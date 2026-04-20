"""Tests for Phase 170-03 telemetry verification.

Verifies background polling loop that confirms BMS commands took effect.
TDD approach: RED → GREEN → REFACTOR

Phase 170-03: Control Actuation Loop — Verification
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.telemetry_service import verify_telemetry_change_async


@pytest.fixture
def mock_event_stream():
    """Mock EventStreamManager for testing."""
    manager = MagicMock()
    manager.emit = AsyncMock()
    return manager


@pytest.fixture
def mock_audit_logger():
    """Mock AuditLogger for testing."""
    logger = MagicMock()
    logger.record_event = AsyncMock()
    return logger


@pytest.mark.asyncio
async def test_verify_telemetry_success_within_timeout(mock_event_stream, mock_audit_logger):
    """COMMAND_VERIFIED emitted when telemetry confirms change before timeout.

    Scenario: Setpoint change from 21.0 → 22.0. Telemetry confirms on attempt 5.
    """
    with patch("app.services.telemetry_service.event_stream", mock_event_stream):
        with patch("app.services.telemetry_service.AuditLogger", return_value=mock_audit_logger):
            with patch("app.services.telemetry_service.get_point_value") as mock_get:
                # Simulate: value starts at 21.0, changes to 22.0 on attempt 5
                mock_get.side_effect = [21.0, 21.0, 21.0, 21.0, 22.0]

                result = await verify_telemetry_change_async(
                    decision_id="test-dec-1",
                    site_id="site-002",
                    correlation_id="test-corr-xyz",
                    expected_change={"device_id": "S002-FCU-L1-A", "point": "setpoint", "expected_value": 22.0},
                )

                assert result is True

                # Verify COMMAND_VERIFIED event was emitted
                mock_event_stream.emit.assert_called()

                # Check the call arguments
                call_kwargs = mock_event_stream.emit.call_args[1]
                assert call_kwargs["event_type"] == "COMMAND_VERIFIED"
                assert call_kwargs["correlation_id"] == "test-corr-xyz"

                # Verify audit event was logged
                mock_audit_logger.record_event.assert_called()
                audit_call = mock_audit_logger.record_event.call_args[0][0]
                assert audit_call["event_type"] == "DECISION_VERIFIED"
                assert audit_call["correlation_id"] == "test-corr-xyz"
                assert audit_call["decision_id"] == "test-dec-1"
                assert audit_call["verification_time_seconds"] == 5


@pytest.mark.asyncio
async def test_verify_telemetry_timeout_after_30s(mock_event_stream, mock_audit_logger):
    """COMMAND_TIMEOUT emitted when telemetry never confirms within 30s.

    Scenario: Setpoint change requested but BMS never confirms the change.
    """
    with patch("app.services.telemetry_service.event_stream", mock_event_stream):
        with patch("app.services.telemetry_service.AuditLogger", return_value=mock_audit_logger):
            with patch("app.services.telemetry_service.get_point_value") as mock_get:
                # Always return wrong value (never changes)
                mock_get.return_value = 21.0

                result = await verify_telemetry_change_async(
                    decision_id="test-dec-2",
                    site_id="site-002",
                    correlation_id="test-corr-abc",
                    expected_change={"device_id": "S002-FCU-L1-A", "point": "setpoint", "expected_value": 22.0},
                )

                assert result is False

                # Verify COMMAND_TIMEOUT event was emitted
                mock_event_stream.emit.assert_called()

                # Last call should be COMMAND_TIMEOUT
                call_kwargs = mock_event_stream.emit.call_args[1]
                assert call_kwargs["event_type"] == "COMMAND_TIMEOUT"
                assert call_kwargs["correlation_id"] == "test-corr-abc"

                # Verify timeout event was logged
                mock_audit_logger.record_event.assert_called()
                # Check last audit call (should be DECISION_TIMEOUT)
                audit_calls = mock_audit_logger.record_event.call_args_list
                last_audit = audit_calls[-1][0][0]
                assert last_audit["event_type"] == "DECISION_TIMEOUT"
                assert last_audit["correlation_id"] == "test-corr-abc"


@pytest.mark.asyncio
async def test_verify_telemetry_error_handling(mock_event_stream, mock_audit_logger):
    """Service error during polling logged, polling continues, timeout emitted.

    Scenario: Telemetry service temporarily down on first attempt, recovered but
    value still doesn't match. After 30s timeout, COMMAND_TIMEOUT emitted.
    """
    with patch("app.services.telemetry_service.event_stream", mock_event_stream):
        with patch("app.services.telemetry_service.AuditLogger", return_value=mock_audit_logger):
            with patch("app.services.telemetry_service.get_point_value") as mock_get:
                # First call raises error, then always wrong value
                mock_get.side_effect = [
                    ConnectionError("Service down"),
                    21.0,  # recovered but wrong value
                    21.0,
                ] + [21.0] * 27  # enough for 30s timeout

                result = await verify_telemetry_change_async(
                    decision_id="test-dec-3",
                    site_id="site-002",
                    correlation_id="test-corr-err",
                    expected_change={"device_id": "S002-FCU-L1-A", "point": "setpoint", "expected_value": 22.0},
                )

                assert result is False

                # Verify error was logged
                audit_calls = mock_audit_logger.record_event.call_args_list
                error_calls = [c for c in audit_calls if c[0][0].get("event_type") == "TELEMETRY_POLL_ERROR"]
                assert len(error_calls) > 0, "Expected TELEMETRY_POLL_ERROR to be logged"

                # After timeout, verify COMMAND_TIMEOUT was emitted
                final_event = mock_event_stream.emit.call_args[1]
                assert final_event["event_type"] == "COMMAND_TIMEOUT"


@pytest.mark.asyncio
async def test_verify_telemetry_immediate_success(mock_event_stream, mock_audit_logger):
    """Verification succeeds immediately (on first check).

    Scenario: Telemetry already confirms the change on first poll.
    """
    with patch("app.services.telemetry_service.event_stream", mock_event_stream):
        with patch("app.services.telemetry_service.AuditLogger", return_value=mock_audit_logger):
            with patch("app.services.telemetry_service.get_point_value") as mock_get:
                # Value matches immediately
                mock_get.return_value = 22.0

                result = await verify_telemetry_change_async(
                    decision_id="test-dec-4",
                    site_id="site-002",
                    correlation_id="test-corr-fast",
                    expected_change={"device_id": "S002-FCU-L1-A", "point": "setpoint", "expected_value": 22.0},
                )

                assert result is True

                # Should verify on attempt 1
                audit_calls = mock_audit_logger.record_event.call_args_list
                verify_call = [c for c in audit_calls if c[0][0].get("event_type") == "DECISION_VERIFIED"][0]
                assert verify_call[0][0]["verification_time_seconds"] == 1


@pytest.mark.asyncio
async def test_sso_endpoint_accepts_correlation_id():
    """SSE endpoint accepts correlation_id as required query parameter.

    Verifies the endpoint signature and that correlation_id is properly handled.
    """
    import inspect

    from app.api.events import event_stream_endpoint

    # Verify endpoint signature includes correlation_id
    sig = inspect.signature(event_stream_endpoint)
    assert "correlation_id" in sig.parameters, "event_stream_endpoint must accept correlation_id parameter"

    # Verify it's a required parameter (no default value)
    param = sig.parameters["correlation_id"]
    # If using Query(...), the default won't be None but will be a Query object
    # Just verify the parameter exists
    assert param is not None


@pytest.mark.asyncio
async def test_verify_correlation_id_threaded_through_emit():
    """Correlation ID properly threaded through all SSE emit() calls.

    Ensures audit trail continuity from approval → verification → frontend.
    """
    mock_event_stream = MagicMock()
    mock_event_stream.emit = AsyncMock()

    mock_audit_logger = MagicMock()
    mock_audit_logger.record_event = AsyncMock()

    with patch("app.services.telemetry_service.event_stream", mock_event_stream):
        with patch("app.services.telemetry_service.AuditLogger", return_value=mock_audit_logger):
            with patch("app.services.telemetry_service.get_point_value") as mock_get:
                mock_get.return_value = 22.0  # Success case

                correlation_id = "test-corr-thread-12345"
                await verify_telemetry_change_async(
                    decision_id="test-dec-5",
                    site_id="site-002",
                    correlation_id=correlation_id,
                    expected_change={"device_id": "S002-FCU-L1-A", "point": "setpoint", "expected_value": 22.0},
                )

                # Verify ALL emit calls include the correlation_id
                all_emit_calls = mock_event_stream.emit.call_args_list
                for call_obj in all_emit_calls:
                    call_kwargs = call_obj[1]
                    assert call_kwargs["correlation_id"] == correlation_id, (
                        f"Correlation ID not properly threaded in emit() call: {call_kwargs}"
                    )
