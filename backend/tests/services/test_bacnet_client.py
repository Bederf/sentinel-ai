"""Tests for BACnet write audit logging.

Verifies:
- BACnetWriteAudit dataclass and log_bacnet_write() method
- Successful BACnet writes produce a BACnetWriteAudit record in JSONL
- Failed BACnet writes log error_msg in the record
- who parameter is threaded through write_point() -> _audit_bacnet_write()
"""

import json
from datetime import datetime
from unittest.mock import MagicMock

import pytest

import app.services.audit_logger as audit_module
from app.services.audit_logger import AuditLogger, BACnetWriteAudit


class TestBACnetWriteAuditDataclass:
    """Tests for BACnetWriteAudit dataclass."""

    def test_bacnet_write_audit_to_dict(self):
        """BACnetWriteAudit.to_dict() produces correct structure."""
        audit = BACnetWriteAudit(
            correlation_id="test corr id",
            equipment_tag="S002-AHU-001-SP",
            device_id=1001,
            object_type="analogValue",
            instance=101,
            value=22.5,
            priority=8,
            who="sentinel",
            timestamp="2026-04-18T10:00:00Z",
            write_latency_ms=12.345,
            success=True,
            error_msg=None,
        )
        d = audit.to_dict()
        assert d["type"] == "bacnet_write"
        assert d["correlation_id"] == "test corr id"
        assert d["equipment_tag"] == "S002-AHU-001-SP"
        assert d["device_id"] == 1001
        assert d["object_type"] == "analogValue"
        assert d["instance"] == 101
        assert d["value"] == 22.5
        assert d["priority"] == 8
        assert d["who"] == "sentinel"
        assert d["timestamp"] == "2026-04-18T10:00:00Z"
        assert d["write_latency_ms"] == 12.35
        assert d["success"] is True
        assert d["error_msg"] is None

    def test_bacnet_write_audit_error_field(self):
        """BACnetWriteAudit.to_dict() includes error_msg when write fails."""
        audit = BACnetWriteAudit(
            correlation_id="test-456",
            equipment_tag="S002-AHU-001-SP",
            device_id=1001,
            object_type="analogValue",
            instance=101,
            value=22.5,
            priority=8,
            who="niagara_bacnet_api",
            timestamp="2026-04-18T10:00:00Z",
            write_latency_ms=0.0,
            success=False,
            error_msg="BACnet service failure",
        )
        d = audit.to_dict()
        assert d["success"] is False
        assert d["error_msg"] == "BACnet service failure"


class TestBACnetWriteAuditLogger:
    """Tests for AuditLogger.log_bacnet_write()."""

    def test_successful_bacnet_write_produces_jsonl_record(self, tmp_path, mocker):
        """log_bacnet_write() appends a correctly structured JSONL record."""
        # Redirect BACNET_AUDIT_DIR to tmp_path
        mock_audit_dir = mocker.patch.object(audit_module, "BACNET_AUDIT_DIR", tmp_path)

        audit_logger = AuditLogger()

        audit = BACnetWriteAudit(
            correlation_id="test-123",
            equipment_tag="S002-AHU-001-SP",
            device_id=1001,
            object_type="analogValue",
            instance=101,
            value=22.5,
            priority=8,
            who="sentinel",
            timestamp=datetime.utcnow().isoformat(),
            write_latency_ms=12.3,
            success=True,
            error_msg=None,
        )
        audit_logger.log_bacnet_write(audit)

        log_file = tmp_path / "bacnet_writes.jsonl"
        assert log_file.exists(), "bacnet_writes.jsonl should be created"
        records = [json.loads(line) for line in open(log_file)]
        assert len(records) == 1
        assert records[0]["equipment_tag"] == "S002-AHU-001-SP"
        assert records[0]["success"] is True
        assert records[0]["error_msg"] is None

    def test_failed_bacnet_write_logs_error_field(self, tmp_path, mocker):
        """Failed BACnet write record includes error_msg."""
        mock_audit_dir = mocker.patch.object(audit_module, "BACNET_AUDIT_DIR", tmp_path)

        audit_logger = AuditLogger()

        audit = BACnetWriteAudit(
            correlation_id="test-456",
            equipment_tag="S002-AHU-001-SP",
            device_id=1001,
            object_type="analogValue",
            instance=101,
            value=22.5,
            priority=8,
            who="sentinel",
            timestamp=datetime.utcnow().isoformat(),
            write_latency_ms=0.0,
            success=False,
            error_msg="BACnet service failure",
        )
        audit_logger.log_bacnet_write(audit)

        log_file = tmp_path / "bacnet_writes.jsonl"
        records = [json.loads(line) for line in open(log_file)]
        assert records[0]["success"] is False
        assert records[0]["error_msg"] == "BACnet service failure"


class TestBACnetClientAuditInstrumentation:
    """Tests for BACnet client _audit_bacnet_write() instrumentation."""

    @pytest.mark.asyncio
    async def test_who_parameter_passed_to_audit(self, mocker):
        """write_point() with who='niagara_bacnet_api' passes that to _audit_bacnet_write."""
        from app.services.niagara.bacnet_client import NiagaraBACnetClient

        client = NiagaraBACnetClient(ip="127.0.0.1", port=47808)
        client._bacnet = MagicMock()
        client._started = True

        audit_spy = mocker.patch.object(NiagaraBACnetClient, "_audit_bacnet_write", return_value=None)
        mocker.patch.object(NiagaraBACnetClient, "_retry_operation", return_value=None)

        await client.write_point(
            device_id=1001,
            object_type="analogValue",
            instance=101,
            value=22.5,
            priority=8,
            who="niagara_bacnet_api",
            correlation_id="corr-999",
        )

        calls = audit_spy.call_args_list
        assert len(calls) == 1, f"Expected 1 audit call, got {len(calls)}: {calls}"
        call_kwargs = calls[0].kwargs
        assert call_kwargs["who"] == "niagara_bacnet_api"
        assert call_kwargs["correlation_id"] == "corr-999"
        assert call_kwargs["success"] is True
        assert call_kwargs["value"] == 22.5

    @pytest.mark.asyncio
    async def test_write_failure_logs_error_in_audit(self, mocker):
        """write_point() that fails logs success=False and error_msg in _audit_bacnet_write."""
        from app.services.niagara.bacnet_client import BACnetWriteError, NiagaraBACnetClient

        client = NiagaraBACnetClient(ip="127.0.0.1", port=47808)
        client._bacnet = MagicMock()
        client._started = True

        audit_spy = mocker.patch.object(NiagaraBACnetClient, "_audit_bacnet_write", return_value=None)

        # Make _retry_operation raise so write fails
        async def fail_write(*args, **kwargs):
            raise BACnetWriteError("Simulated failure")

        mocker.patch.object(NiagaraBACnetClient, "_retry_operation", fail_write)

        with pytest.raises(BACnetWriteError):
            await client.write_point(
                device_id=1001,
                object_type="analogValue",
                instance=101,
                value=22.5,
                priority=8,
                who="sentinel",
                correlation_id="corr-fail",
            )

        # Audit should have been called with success=False
        calls = audit_spy.call_args_list
        assert len(calls) == 1
        call_kwargs = calls[0].kwargs
        assert call_kwargs["success"] is False
        assert "Simulated failure" in call_kwargs["error_msg"]
