"""Tests for audit logger service.

Tests cover:
- Audit log rotation and archival
- Immutable audit trail storage
- Audit entry retention policy
"""

import pytest
from datetime import datetime, timedelta
import json
from unittest.mock import patch, MagicMock

from app.services.audit_logger import AuditLogger
from app.models.audit_log import AuditLogEntry, AuditActionType, AuditResultType


@pytest.mark.asyncio
class TestAuditLogRotation:
    """Test audit log rotation and archival functionality.

    Control: AUDIT-001 (Immutable Audit Trail)
    """

    @pytest.fixture
    def audit_logger(self, tmp_path):
        """Create AuditLogger instance with temp log file."""
        # Create new instance (not singleton)
        logger = AuditLogger.__new__(AuditLogger)
        logger._initialized = False
        logger.log_file = tmp_path / "audit_log.json"
        logger.log_file.parent.mkdir(exist_ok=True, parents=True)
        logger.max_entries = 10_000
        logger.buffer = []
        logger.buffer_size = 10
        logger.encryption_service = MagicMock()
        logger.encryption_service.enabled = False
        logger._write_lock = __import__("threading").Lock()
        logger._lock = __import__("threading").Lock()
        return logger

    async def _create_audit_entries(self, logger, count: int, days_old: int = 0) -> list:
        """Helper to create audit entries."""
        entries = []
        for i in range(count):
            # Create timestamp: days_old days in the past
            timestamp = datetime.now() - timedelta(days=days_old)
            entry = AuditLogEntry(
                id=f"entry-{i}",
                timestamp=timestamp,
                action=AuditActionType.DEVICE_CONTROL,
                user="test-user",
                device_id=f"device-{i}",
                point_name="setpoint",
                old_value=20.0,
                new_value=25.0,
                result=AuditResultType.SUCCESS,
            )
            entries.append(entry)
        return entries

    @pytest.mark.asyncio
    async def test_audit_log_rotation_old_entries(self, audit_logger):
        """Test that archival moves old entries and keeps new ones.

        Creates 10 old entries (31 days old) and 5 new entries (1 day old).
        After archival with days_old=30, should have:
        - 10 entries archived (attempted)
        - 5 entries remaining in active log

        Control: AUDIT-001 (Immutable Audit Trail)
        """
        # Create 10 old entries (31 days ago)
        old_entries = await self._create_audit_entries(audit_logger, count=10, days_old=31)

        # Create 5 new entries (1 day ago)
        new_entries = await self._create_audit_entries(audit_logger, count=5, days_old=1)

        # Save all entries to active log
        all_entries = old_entries + new_entries
        audit_logger._save_logs(all_entries)

        # Mock Supabase client for archival
        mock_supabase = MagicMock()
        mock_table = MagicMock()
        mock_upsert = MagicMock()
        mock_table.upsert = MagicMock(return_value=mock_upsert)
        mock_upsert.execute = MagicMock()
        mock_supabase.table = MagicMock(return_value=mock_table)

        with patch(
            "app.database.supabase_client.get_supabase_client",
            return_value=mock_supabase,
        ):
            # Run archival for entries > 30 days old
            archived_count = await audit_logger.archive_old_audit_logs(days_old=30)

        # Verify 10 entries were archived
        assert archived_count == 10, f"Expected 10 archived entries, got {archived_count}"

        # Verify active log now has only 5 entries (new ones)
        with open(audit_logger.log_file, "r") as f:
            data = json.load(f)
            remaining = data.get("entries", [])
            assert len(remaining) == 5, f"Expected 5 remaining entries in active log, got {len(remaining)}"

    @pytest.mark.asyncio
    async def test_audit_log_rotation_no_old_entries(self, audit_logger):
        """Test archival when no entries are old enough."""
        # Create only new entries (1 day old)
        new_entries = await self._create_audit_entries(audit_logger, count=10, days_old=1)
        audit_logger._save_logs(new_entries)

        # Run archival for entries > 30 days old (none should qualify)
        archived_count = await audit_logger.archive_old_audit_logs(days_old=30)

        # Verify no entries were archived
        assert archived_count == 0, f"Expected 0 archived entries, got {archived_count}"

        # Verify all 10 entries remain in active log
        with open(audit_logger.log_file, "r") as f:
            data = json.load(f)
            remaining = data.get("entries", [])
            assert len(remaining) == 10

    @pytest.mark.asyncio
    async def test_audit_log_rotation_idempotent(self, audit_logger):
        """Test that archival is idempotent (safe to run multiple times)."""
        # Create 10 old entries (31 days ago)
        old_entries = await self._create_audit_entries(audit_logger, count=10, days_old=31)
        audit_logger._save_logs(old_entries)

        # Mock Supabase with upsert (idempotent insert/update)
        mock_supabase = MagicMock()
        mock_table = MagicMock()
        mock_upsert = MagicMock()
        mock_table.upsert = MagicMock(return_value=mock_upsert)
        mock_upsert.execute = MagicMock()
        mock_supabase.table = MagicMock(return_value=mock_table)

        with patch(
            "app.database.supabase_client.get_supabase_client",
            return_value=mock_supabase,
        ):
            # Run archival first time
            archived1 = await audit_logger.archive_old_audit_logs(days_old=30)
            assert archived1 == 10

            # Run archival second time (should be no-op — no entries left)
            archived2 = await audit_logger.archive_old_audit_logs(days_old=30)
            assert archived2 == 0, f"Second archival should find no entries, got {archived2}"

    @pytest.mark.asyncio
    async def test_audit_log_archival_failure_preserves_active(self, audit_logger):
        """Test that if archival fails, active log is preserved."""
        # Create 10 old entries
        old_entries = await self._create_audit_entries(audit_logger, count=10, days_old=31)
        audit_logger._save_logs(old_entries)

        # Mock Supabase to fail
        mock_supabase = MagicMock()
        mock_table = MagicMock()
        mock_upsert = MagicMock()
        mock_table.upsert = MagicMock(return_value=mock_upsert)
        mock_upsert.execute = MagicMock(side_effect=Exception("Supabase connection error"))
        mock_supabase.table = MagicMock(return_value=mock_table)

        with patch(
            "app.database.supabase_client.get_supabase_client",
            return_value=mock_supabase,
        ):
            # Run archival (should fail gracefully)
            archived_count = await audit_logger.archive_old_audit_logs(days_old=30)

        # Verify archival returned 0 (failed)
        assert archived_count == 0

        # Verify original 10 entries are still in active log
        with open(audit_logger.log_file, "r") as f:
            data = json.load(f)
            remaining = data.get("entries", [])
            # All 10 should still be there since archival failed
            assert len(remaining) == 10, f"Expected 10 entries preserved after failed archival, got {len(remaining)}"

    @pytest.mark.asyncio
    async def test_audit_archival_background_job_scheduling(self, audit_logger):
        """Test background job creation for periodic archival.

        Note: This test verifies that the job method exists and can be created,
        not that it actually runs indefinitely (which would block the test).
        """
        # Verify job method exists
        assert hasattr(audit_logger, "audit_archival_job")
        assert callable(audit_logger.audit_archival_job)

        # Verify job can be created (would need to be cancelled in real usage)
        # This just tests structure, not actual execution
        job_coro = audit_logger.audit_archival_job(interval_days=30)
        assert job_coro is not None

        # Cancel the coroutine (don't actually run it)
        job_coro.close()
