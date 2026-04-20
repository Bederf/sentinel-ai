"""Tests for unified execution service.

Covers the three required cases:
1. Success — write ok, value matches, verified=True
2. Mismatch — write ok, value != expected, verified=False
3. Failure — device write fails, success=False, audit still written
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.execution_service import execute_command

SITE_ID = "site-001"
EQUIPMENT_ID = "S001-AHU-B1-001"
CONTROL_POINT = "setpoint"
TARGET_VALUE = 22.5
CORRELATION_ID = "corr-test-001"
DECISION_ID = "dec-test-001"


@pytest.fixture
def mock_cov_result_verified():
    result = MagicMock()
    result.verified = True
    result.actual_value = TARGET_VALUE
    result.expected_value = TARGET_VALUE
    result.read_success = True
    result.elapsed_seconds = 0.1
    result.error = None
    return result


@pytest.fixture
def mock_cov_result_mismatch():
    result = MagicMock()
    result.verified = False
    result.actual_value = 19.0  # different from target
    result.expected_value = TARGET_VALUE
    result.read_success = True
    result.elapsed_seconds = 0.1
    result.error = None
    return result


class TestExecuteCommandSuccess:
    """Write ok, value matches — verified=True."""

    @pytest.mark.asyncio
    async def test_success_returns_verified_true(self, mock_cov_result_verified):
        mock_audit_repo = MagicMock()
        mock_cov_service = AsyncMock()
        mock_cov_service.verify_write = AsyncMock(return_value=mock_cov_result_verified)

        with (
            patch("app.services.execution_service.device_manager") as mock_dm,
            patch("app.services.execution_service.get_cov_monitor_service", return_value=mock_cov_service),
            patch("app.services.execution_service.AuditRepository", return_value=mock_audit_repo),
        ):
            mock_dm.write_device_value = AsyncMock(return_value=True)

            result = await execute_command(
                site_id=SITE_ID,
                equipment_id=EQUIPMENT_ID,
                control_point=CONTROL_POINT,
                target_value=TARGET_VALUE,
                source="advisory",
                correlation_id=CORRELATION_ID,
                decision_id=DECISION_ID,
            )

        assert result["success"] is True
        assert result["verified"] is True
        assert result["actual_value"] == TARGET_VALUE
        assert result["expected_value"] == TARGET_VALUE
        assert result["error"] is None
        assert result["correlation_id"] == CORRELATION_ID

    @pytest.mark.asyncio
    async def test_success_calls_device_write_with_correct_args(self, mock_cov_result_verified):
        mock_cov_service = AsyncMock()
        mock_cov_service.verify_write = AsyncMock(return_value=mock_cov_result_verified)

        with (
            patch("app.services.execution_service.device_manager") as mock_dm,
            patch("app.services.execution_service.get_cov_monitor_service", return_value=mock_cov_service),
            patch("app.services.execution_service.AuditRepository", return_value=MagicMock()),
        ):
            mock_dm.write_device_value = AsyncMock(return_value=True)

            await execute_command(
                site_id=SITE_ID,
                equipment_id=EQUIPMENT_ID,
                control_point=CONTROL_POINT,
                target_value=TARGET_VALUE,
                source="advisory",
                correlation_id=CORRELATION_ID,
            )

        mock_dm.write_device_value.assert_awaited_once_with(
            device_id=EQUIPMENT_ID,
            point_name=CONTROL_POINT,
            value=TARGET_VALUE,
            priority=8,
        )

    @pytest.mark.asyncio
    async def test_success_writes_audit_record(self, mock_cov_result_verified):
        mock_audit_repo = MagicMock()
        mock_cov_service = AsyncMock()
        mock_cov_service.verify_write = AsyncMock(return_value=mock_cov_result_verified)

        with (
            patch("app.services.execution_service.device_manager") as mock_dm,
            patch("app.services.execution_service.get_cov_monitor_service", return_value=mock_cov_service),
            patch("app.services.execution_service.AuditRepository", return_value=mock_audit_repo),
        ):
            mock_dm.write_device_value = AsyncMock(return_value=True)

            await execute_command(
                site_id=SITE_ID,
                equipment_id=EQUIPMENT_ID,
                control_point=CONTROL_POINT,
                target_value=TARGET_VALUE,
                source="advisory",
                correlation_id=CORRELATION_ID,
            )

        mock_audit_repo.log_device_control.assert_called_once()
        call_kwargs = mock_audit_repo.log_device_control.call_args
        assert call_kwargs.kwargs["result"] == "SUCCESS"
        assert call_kwargs.kwargs["metadata"]["verified"] is True
        assert call_kwargs.kwargs["metadata"]["source"] == "advisory"


class TestExecuteCommandMismatch:
    """Write ok, value != expected — verified=False, success=True."""

    @pytest.mark.asyncio
    async def test_mismatch_returns_verified_false(self, mock_cov_result_mismatch):
        mock_cov_service = AsyncMock()
        mock_cov_service.verify_write = AsyncMock(return_value=mock_cov_result_mismatch)

        with (
            patch("app.services.execution_service.device_manager") as mock_dm,
            patch("app.services.execution_service.get_cov_monitor_service", return_value=mock_cov_service),
            patch("app.services.execution_service.AuditRepository", return_value=MagicMock()),
        ):
            mock_dm.write_device_value = AsyncMock(return_value=True)

            result = await execute_command(
                site_id=SITE_ID,
                equipment_id=EQUIPMENT_ID,
                control_point=CONTROL_POINT,
                target_value=TARGET_VALUE,
                source="advisory",
                correlation_id=CORRELATION_ID,
            )

        assert result["success"] is True  # write itself succeeded
        assert result["verified"] is False  # but read-back didn't match
        assert result["actual_value"] == 19.0
        assert result["error"] is None

    @pytest.mark.asyncio
    async def test_mismatch_still_writes_audit(self, mock_cov_result_mismatch):
        mock_audit_repo = MagicMock()
        mock_cov_service = AsyncMock()
        mock_cov_service.verify_write = AsyncMock(return_value=mock_cov_result_mismatch)

        with (
            patch("app.services.execution_service.device_manager") as mock_dm,
            patch("app.services.execution_service.get_cov_monitor_service", return_value=mock_cov_service),
            patch("app.services.execution_service.AuditRepository", return_value=mock_audit_repo),
        ):
            mock_dm.write_device_value = AsyncMock(return_value=True)

            await execute_command(
                site_id=SITE_ID,
                equipment_id=EQUIPMENT_ID,
                control_point=CONTROL_POINT,
                target_value=TARGET_VALUE,
                source="advisory",
                correlation_id=CORRELATION_ID,
            )

        mock_audit_repo.log_device_control.assert_called_once()
        call_kwargs = mock_audit_repo.log_device_control.call_args
        assert call_kwargs.kwargs["metadata"]["verified"] is False


class TestExecuteCommandFailure:
    """Device write fails — success=False, audit still written."""

    @pytest.mark.asyncio
    async def test_write_exception_returns_success_false(self):
        mock_audit_repo = MagicMock()

        with (
            patch("app.services.execution_service.device_manager") as mock_dm,
            patch("app.services.execution_service.get_cov_monitor_service"),
            patch("app.services.execution_service.AuditRepository", return_value=mock_audit_repo),
        ):
            mock_dm.write_device_value = AsyncMock(side_effect=RuntimeError("BACnet timeout"))

            result = await execute_command(
                site_id=SITE_ID,
                equipment_id=EQUIPMENT_ID,
                control_point=CONTROL_POINT,
                target_value=TARGET_VALUE,
                source="advisory",
                correlation_id=CORRELATION_ID,
            )

        assert result["success"] is False
        assert result["verified"] is False
        assert result["actual_value"] is None
        assert "BACnet timeout" in result["error"]

    @pytest.mark.asyncio
    async def test_write_failure_audit_still_written(self):
        mock_audit_repo = MagicMock()

        with (
            patch("app.services.execution_service.device_manager") as mock_dm,
            patch("app.services.execution_service.get_cov_monitor_service"),
            patch("app.services.execution_service.AuditRepository", return_value=mock_audit_repo),
        ):
            mock_dm.write_device_value = AsyncMock(side_effect=RuntimeError("BACnet timeout"))

            await execute_command(
                site_id=SITE_ID,
                equipment_id=EQUIPMENT_ID,
                control_point=CONTROL_POINT,
                target_value=TARGET_VALUE,
                source="advisory",
                correlation_id=CORRELATION_ID,
            )

        # Audit must fire even on exception
        mock_audit_repo.log_device_control.assert_called_once()
        call_kwargs = mock_audit_repo.log_device_control.call_args
        assert call_kwargs.kwargs["result"] == "FAILED"

    @pytest.mark.asyncio
    async def test_write_returns_false_treated_as_failure(self):
        mock_audit_repo = MagicMock()
        mock_cov_service = AsyncMock()

        with (
            patch("app.services.execution_service.device_manager") as mock_dm,
            patch("app.services.execution_service.get_cov_monitor_service", return_value=mock_cov_service),
            patch("app.services.execution_service.AuditRepository", return_value=mock_audit_repo),
        ):
            mock_dm.write_device_value = AsyncMock(return_value=False)

            result = await execute_command(
                site_id=SITE_ID,
                equipment_id=EQUIPMENT_ID,
                control_point=CONTROL_POINT,
                target_value=TARGET_VALUE,
                source="manual",
                correlation_id=CORRELATION_ID,
            )

        assert result["success"] is False
        # COV should not be called when write failed
        mock_cov_service.verify_write.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_audit_failure_does_not_raise(self):
        """An audit write error must not propagate — execution result is primary."""
        mock_audit_repo = MagicMock()
        mock_audit_repo.log_device_control.side_effect = Exception("DB unreachable")
        mock_cov_service = AsyncMock()
        mock_cov_result = MagicMock()
        mock_cov_result.verified = True
        mock_cov_result.actual_value = TARGET_VALUE
        mock_cov_service.verify_write = AsyncMock(return_value=mock_cov_result)

        with (
            patch("app.services.execution_service.device_manager") as mock_dm,
            patch("app.services.execution_service.get_cov_monitor_service", return_value=mock_cov_service),
            patch("app.services.execution_service.AuditRepository", return_value=mock_audit_repo),
        ):
            mock_dm.write_device_value = AsyncMock(return_value=True)

            # Must not raise even though audit write throws
            result = await execute_command(
                site_id=SITE_ID,
                equipment_id=EQUIPMENT_ID,
                control_point=CONTROL_POINT,
                target_value=TARGET_VALUE,
                source="advisory",
                correlation_id=CORRELATION_ID,
            )

        assert result["success"] is True
        assert result["verified"] is True
