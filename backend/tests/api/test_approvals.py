"""
Integration tests for Tier 2 approval workflow (Phase 68-02 Task 3)

Tests cover:
- Approval with SafetyEngine validation
- Device write execution and COV verification
- Rejection workflow
- Rollback mechanism
- Error handling (safety violations, device failures)
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.recommendation import Recommendation, RecommendationStatus
from app.services.approval_service import ApprovalService


@pytest.fixture
def mock_recommendation():
    """Create a mock recommendation for testing."""
    return Recommendation(
        id="rec-123",
        target_equipment="S002-CHILLER-B1-001",
        action={"point": "setpoint", "value": 20.0},
        confidence="high",
        reason="Peak demand response",
        status=RecommendationStatus.PENDING,
    )


@pytest.fixture
def approval_service():
    """Create an ApprovalService instance with mocked dependencies."""
    service = ApprovalService()
    service.recommendations_repo = AsyncMock()
    service.audit_repo = AsyncMock()
    service.device_manager = AsyncMock()
    service.safety_engine = MagicMock()
    service.safety_engine.initialize = AsyncMock()
    # _validate_safety is the actual method called during execute_approval
    service._validate_safety = AsyncMock(return_value={"is_safe": True})
    return service


class TestApprovalExecution:
    """Tests for approval execution workflow."""

    @pytest.mark.asyncio
    async def test_approve_recommendation_success(self, approval_service, mock_recommendation):
        """Should approve recommendation and execute device control."""
        # Setup mocks
        approval_service.recommendations_repo.get_by_id.return_value = mock_recommendation
        approval_service._validate_safety = AsyncMock(return_value={"is_safe": True})
        # Mock read_device_value for original value capture (rollback)
        original_reading = MagicMock()
        original_reading.value = 18.0
        approval_service.device_manager.read_device_value = AsyncMock(return_value=original_reading)
        approval_service.audit_repo.log_action.return_value = None

        # execute_approval now routes through execution_service.execute_command —
        # patch it at the module where it is imported (approval_service does a
        # local `from app.services.execution_service import execute_command`).
        exec_result = {
            "success": True,
            "verified": True,
            "actual_value": 20.0,
            "expected_value": 20.0,
            "error": None,
            "correlation_id": "test-corr",
        }
        with patch("app.services.execution_service.execute_command", new=AsyncMock(return_value=exec_result)):
            # Execute approval
            result = await approval_service.execute_approval(
                recommendation_id="rec-123", approved_by="technician@site-002", approval_notes="Urgent - peak demand"
            )

        # Verify result
        assert result.success is True
        assert result.status == "executed"
        assert result.recommendation_id == "rec-123"
        assert result.cov_verified is True
        assert result.execution_result is not None
        assert result.execution_result["original_value"] == 18.0

        # Verify method calls
        approval_service.recommendations_repo.get_by_id.assert_called_once_with("rec-123")
        approval_service._validate_safety.assert_called_once()
        approval_service.audit_repo.log_action.assert_called_once()

    @pytest.mark.asyncio
    async def test_approve_fails_safety_validation(self, approval_service, mock_recommendation):
        """Should reject approval if SafetyEngine validation fails."""
        # Setup mocks
        approval_service.recommendations_repo.get_by_id.return_value = mock_recommendation
        approval_service._validate_safety = AsyncMock(
            return_value={"is_safe": False, "reason": "Temperature below minimum allowed (4°C)"}
        )

        # Execute approval
        result = await approval_service.execute_approval(recommendation_id="rec-123", approved_by="technician@site-002")

        # Verify result
        assert result.success is False
        assert result.status == "rejected"
        assert "Safety constraint violation" in result.error_message

        # Verify device write was NOT called
        approval_service.device_manager.set_value.assert_not_called()

    @pytest.mark.asyncio
    async def test_approve_fails_device_write(self, approval_service, mock_recommendation):
        """Should handle device write failure gracefully."""
        # Setup mocks
        approval_service.recommendations_repo.get_by_id.return_value = mock_recommendation
        approval_service._validate_safety = AsyncMock(return_value={"is_safe": True})
        original_reading = MagicMock()
        original_reading.value = 18.0
        approval_service.device_manager.read_device_value = AsyncMock(return_value=original_reading)
        approval_service.device_manager.write_device_value = AsyncMock(
            side_effect=Exception("Device communication timeout")
        )

        # Execute approval
        result = await approval_service.execute_approval(recommendation_id="rec-123", approved_by="technician@site-002")

        # Verify result
        assert result.success is False
        assert result.status == "failed"
        assert "Device" in result.error_message or "timeout" in result.error_message.lower()

    @pytest.mark.asyncio
    async def test_approve_cov_feedback_mismatch(self, approval_service, mock_recommendation):
        """Should flag COV feedback mismatch but still approve."""
        # Setup mocks
        approval_service.recommendations_repo.get_by_id.return_value = mock_recommendation
        approval_service._validate_safety = AsyncMock(return_value={"is_safe": True})
        original_reading = MagicMock()
        original_reading.value = 18.0
        approval_service.device_manager.read_device_value = AsyncMock(return_value=original_reading)
        approval_service.audit_repo.log_action.return_value = None

        # execute_approval now routes through execution_service.execute_command.
        # Simulate a write-success but COV mismatch (wrote 20.0, read back 15.0).
        exec_result = {
            "success": True,
            "verified": False,  # COV mismatch
            "actual_value": 15.0,
            "expected_value": 20.0,
            "error": None,
            "correlation_id": "test-corr",
        }
        with patch("app.services.execution_service.execute_command", new=AsyncMock(return_value=exec_result)):
            # Execute approval
            result = await approval_service.execute_approval(
                recommendation_id="rec-123", approved_by="technician@site-002"
            )

        # Verify result
        assert result.success is True  # Still succeeds
        assert result.cov_verified is False  # But flag the mismatch


class TestRecommendationRejection:
    """Tests for recommendation rejection workflow."""

    @pytest.mark.asyncio
    async def test_reject_recommendation_success(self, approval_service, mock_recommendation):
        """Should reject recommendation and record reason."""
        # Setup mocks
        approval_service.recommendations_repo.get_by_id.return_value = mock_recommendation
        approval_service.audit_repo.log_action.return_value = None

        # Execute rejection
        result = await approval_service.reject_approval(
            recommendation_id="rec-123",
            rejected_by="supervisor@site-002",
            reason="Conflicting with scheduled maintenance",
        )

        # Verify result
        assert result.success is True
        assert result.status == "rejected"
        assert result.recommendation_id == "rec-123"

        # Verify method calls
        approval_service.recommendations_repo.get_by_id.assert_called_once()
        approval_service.audit_repo.log_action.assert_called_once()

    @pytest.mark.asyncio
    async def test_reject_nonexistent_recommendation(self, approval_service):
        """Should handle rejection of nonexistent recommendation."""
        # Setup mocks
        approval_service.recommendations_repo.get_by_id.return_value = None

        # Execute rejection
        result = await approval_service.reject_approval(
            recommendation_id="nonexistent", rejected_by="supervisor@site-002", reason="Test"
        )

        # Verify result
        assert result.success is False
        assert "not found" in result.error_message


class TestRollbackMechanism:
    """Tests for rollback of executed approvals."""

    @pytest.mark.asyncio
    async def test_rollback_executed_approval_success(self, approval_service, mock_recommendation):
        """Should rollback executed approval to original state."""
        # Setup recommendation with execution history
        executed_rec = Recommendation(
            id="rec-123",
            target_equipment="S002-CHILLER-B1-001",
            action={"point": "setpoint", "value": 20.0},
            confidence="high",
            reason="Peak demand response",
            status=RecommendationStatus.EXECUTED,
            execution_result={
                "success": True,
                "original_value": 18.0,
                "target_value": 20.0,
                "control_point": "setpoint",
            },
        )

        # Setup mocks
        approval_service.recommendations_repo.get_by_id.return_value = executed_rec
        approval_service.device_manager.write_device_value = AsyncMock(return_value=True)
        rollback_cov = MagicMock()
        rollback_cov.value = 18.0
        approval_service.device_manager.read_device_value = AsyncMock(return_value=rollback_cov)
        approval_service.audit_repo.log_action.return_value = None

        # Execute rollback
        result = await approval_service.rollback_approval(
            recommendation_id="rec-123", rollback_reason="Error in recommendation", initiated_by="technician@site-002"
        )

        # Verify result
        assert result.success is True
        assert result.status == "rolled_back"
        assert result.cov_verified is True

        # Verify device write was called for rollback
        approval_service.device_manager.write_device_value.assert_called_once()

        # Verify audit log
        approval_service.audit_repo.log_action.assert_called_once()

    @pytest.mark.asyncio
    async def test_rollback_nonexecuted_recommendation(self, approval_service, mock_recommendation):
        """Should reject rollback of non-executed recommendation."""
        # Setup mocks
        approval_service.recommendations_repo.get_by_id.return_value = mock_recommendation

        # Execute rollback
        result = await approval_service.rollback_approval(
            recommendation_id="rec-123", rollback_reason="Test", initiated_by="technician@site-002"
        )

        # Verify result
        assert result.success is False
        assert "Cannot rollback" in result.error_message
        assert "Only executed recommendations" in result.error_message

    @pytest.mark.asyncio
    async def test_rollback_fails_missing_state(self, approval_service):
        """Should handle rollback when original state is missing."""
        # Setup recommendation with incomplete execution_result
        incomplete_rec = Recommendation(
            id="rec-456",
            target_equipment="S002-AHU-L1-A",
            action={"point": "vav_flow", "value": 1500},
            confidence="medium",
            reason="Flow optimization",
            status=RecommendationStatus.EXECUTED,
            execution_result={},  # Missing original_value and control_point
        )

        # Setup mocks
        approval_service.recommendations_repo.get_by_id.return_value = incomplete_rec

        # Execute rollback
        result = await approval_service.rollback_approval(
            recommendation_id="rec-456", rollback_reason="Test", initiated_by="technician@site-002"
        )

        # Verify result
        assert result.success is False
        assert "missing original state" in result.error_message


class TestApprovalValidation:
    """Tests for approval validation."""

    @pytest.mark.asyncio
    async def test_validate_approval_pending_recommendation(self, approval_service, mock_recommendation):
        """Should validate pending recommendation."""
        # Setup mocks
        approval_service.recommendations_repo.get_by_id.return_value = mock_recommendation

        # Validate
        is_valid, error_msg = await approval_service.validate_approval(
            recommendation_id="rec-123", approved_by="technician@site-002"
        )

        # Verify result
        assert is_valid is True
        assert error_msg == ""

    @pytest.mark.asyncio
    async def test_validate_approval_nonexistent(self, approval_service):
        """Should reject validation for nonexistent recommendation."""
        # Setup mocks
        approval_service.recommendations_repo.get_by_id.return_value = None

        # Validate
        is_valid, error_msg = await approval_service.validate_approval(
            recommendation_id="nonexistent", approved_by="technician@site-002"
        )

        # Verify result
        assert is_valid is False
        assert "not found" in error_msg

    @pytest.mark.asyncio
    async def test_validate_approval_already_executed(self, approval_service, mock_recommendation):
        """Should reject validation for already executed recommendation."""
        # Setup
        executed_rec = Recommendation(
            id="rec-123",
            target_equipment="S002-CHILLER-B1-001",
            action={"point": "setpoint", "value": 20.0},
            confidence="high",
            reason="Peak demand response",
            status=RecommendationStatus.EXECUTED,
        )

        # Setup mocks
        approval_service.recommendations_repo.get_by_id.return_value = executed_rec

        # Validate
        is_valid, error_msg = await approval_service.validate_approval(
            recommendation_id="rec-123", approved_by="technician@site-002"
        )

        # Verify result
        assert is_valid is False
        assert "not pending approval" in error_msg
