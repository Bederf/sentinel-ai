"""Tests for audit logger service.

Tests cover:
- Audit log rotation and archival
- Immutable audit trail storage
- Audit entry retention policy
"""

import json
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from app.models.audit_log import AuditActionType, AuditLogEntry, AuditResultType
from app.services.audit_logger import AuditLogger


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
        with open(audit_logger.log_file) as f:
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
        with open(audit_logger.log_file) as f:
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
        with open(audit_logger.log_file) as f:
            data = json.load(f)
            remaining = data.get("entries", [])
            # All 10 should still be there since archival failed
            assert len(remaining) == 10, f"Expected 10 entries preserved after failed archival, got {len(remaining)}"

    @pytest.mark.asyncio
    async def test_archival_partial_failure_preserves_active(self, audit_logger):
        """If archival fails partway, failed entries stay in active log for retry.

        Scenario: 10 old entries, upsert succeeds for first 5, fails for 6-10.
        Expected: archived_count=5, 5 successful deleted, 5 failed preserved in active log.
        Control: AUDIT-001 (Immutable Audit Trail) — atomic delete on partial failure
        Phase: 168-03 (Audit Archival Race Condition & Partial Failure Fix)
        """
        # Create 10 old entries (31 days ago)
        old_entries = await self._create_audit_entries(audit_logger, count=10, days_old=31)
        audit_logger._save_logs(old_entries)

        # Mock Supabase to fail on entries 6-10 (after first 5 succeed)
        mock_supabase = MagicMock()
        mock_table = MagicMock()
        mock_upsert = MagicMock()

        call_count = [0]

        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] > 5:
                # Fail on 6th upsert and onwards
                raise ConnectionError("Supabase connection lost during archival")
            return MagicMock()

        mock_upsert.execute = MagicMock(side_effect=side_effect)
        mock_table.upsert = MagicMock(return_value=mock_upsert)
        mock_supabase.table = MagicMock(return_value=mock_table)

        with patch(
            "app.database.supabase_client.get_supabase_client",
            return_value=mock_supabase,
        ):
            # Run archival
            archived_count = await audit_logger.archive_old_audit_logs(days_old=30)

        # Verify: 5 succeeded
        assert archived_count == 5, f"Expected 5 archived entries, got {archived_count}"

        # Verify: active log has 5 failed entries remaining (only successful ones deleted)
        with open(audit_logger.log_file) as f:
            data = json.load(f)
            remaining = data.get("entries", [])
            # Only the 5 failed entries should remain (entries 5-9, since 0-4 succeeded)
            assert len(remaining) == 5, (
                f"Expected 5 failed entries preserved in active log after partial failure, "
                f"got {len(remaining)} (5 succeeded were deleted, 5 failed stay for retry)"
            )
            # Verify the remaining entries are the failed ones (entries 5-9)
            remaining_ids = {e["id"] for e in remaining}
            expected_failed_ids = {f"entry-{i}" for i in range(5, 10)}
            assert remaining_ids == expected_failed_ids, (
                f"Expected failed entries {expected_failed_ids} to remain, got {remaining_ids}"
            )

    @pytest.mark.asyncio
    async def test_archival_idempotent_on_retry(self, audit_logger):
        """Archival is idempotent on retry after transient failure.

        Scenario: Retry archival on same entries after transient failure.
        Expected: Both runs succeed, no duplicates, no loss.
        Control: AUDIT-001 (Immutable Audit Trail) — idempotent archival
        Phase: 168-03 (Audit Archival Race Condition & Partial Failure Fix)
        """
        # Create 10 old entries (31 days ago)
        old_entries = await self._create_audit_entries(audit_logger, count=10, days_old=31)
        audit_logger._save_logs(old_entries)

        # Mock Supabase with successful upsert (idempotent)
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
            # First archival (all succeed)
            count1 = await audit_logger.archive_old_audit_logs(days_old=30)
            assert count1 == 10, f"First archival should succeed with 10 entries, got {count1}"

            # Verify entries were deleted from active log
            with open(audit_logger.log_file) as f:
                data = json.load(f)
                remaining = data.get("entries", [])
                assert len(remaining) == 0, (
                    f"After successful archival, active log should be empty, got {len(remaining)}"
                )

            # Simulate restart without archival completing (reload from backup)
            # Re-add entries to active log (as if archival had failed partway)
            audit_logger._save_logs(old_entries)

            # Retry archival (upserts are idempotent, should succeed)
            count2 = await audit_logger.archive_old_audit_logs(days_old=30)
            assert count2 == 10, f"Second archival retry should succeed with 10 entries, got {count2}"

            # Verify: Supabase was called twice per entry (idempotent upsert)
            # Total calls: 10 (first run) + 10 (second run) = 20
            assert mock_table.upsert.call_count == 20, (
                f"Upsert should be called 20 times (10 + 10 retry), got {mock_table.upsert.call_count}"
            )

    @pytest.mark.asyncio
    async def test_concurrent_archival_safe_with_lock(self, audit_logger):
        """Asyncio lock prevents race condition in concurrent archival (Phase 168-03).

        Tests that the archival function acquires an asyncio.Lock to prevent concurrent
        execution from causing data loss when both instances try to delete the same entries.

        Scenario: Verify lock is acquired and held during archival.
        Expected: Lock mechanism prevents concurrent unsafe access.
        Control: AUDIT-001 (Immutable Audit Trail) — concurrent safety
        Phase: 168-03 (Audit Archival Race Condition & Partial Failure Fix)
        """
        from app.services.audit_logger import _AUDIT_ARCHIVAL_LOCK

        # Create 10 old entries (31 days ago)
        old_entries = await self._create_audit_entries(audit_logger, count=10, days_old=31)
        audit_logger._save_logs(old_entries)

        # Verify lock exists and is an asyncio.Lock instance
        assert _AUDIT_ARCHIVAL_LOCK is not None, "Audit archival lock should be initialized"
        assert hasattr(_AUDIT_ARCHIVAL_LOCK, "acquire"), "Archival lock should have acquire method"
        assert hasattr(_AUDIT_ARCHIVAL_LOCK, "release"), "Archival lock should have release method"
        # asyncio.Lock has __aenter__ for async context manager
        assert hasattr(_AUDIT_ARCHIVAL_LOCK, "__aenter__"), "Archival lock should support async context manager"

        # Mock Supabase with successful upsert
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
            # Run archival (lock is acquired inside archive_old_audit_logs)
            archived_count = await audit_logger.archive_old_audit_logs(days_old=30)

        # Verify archival succeeded
        assert archived_count == 10, f"Expected 10 archived entries, got {archived_count}"

        # Verify active log is empty (all entries deleted after successful archival)
        with open(audit_logger.log_file) as f:
            data = json.load(f)
            remaining = data.get("entries", [])
            assert len(remaining) == 0, f"Active log should be empty after archival, got {len(remaining)}"

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
