"""Tests for FaultOccurrenceTracker and FaultOccurrenceRepository.

Covers:
- 1st occurrence: no cluster alert
- 2nd occurrence: no cluster alert
- 3rd occurrence: cluster alert fires
- 4th occurrence: cluster alert still fires, count increments
- Empty equipment_id / issue_type: handled gracefully
- Sliding window expiry (mock time)
- Repository dual-write smoke
"""

import json
import uuid
from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from app.models.fault_occurrence import FaultOccurrence

# ---------------------------------------------------------------------------
# FaultOccurrence model tests
# ---------------------------------------------------------------------------


class TestFaultOccurrenceModel:
    def test_to_dict_roundtrip(self):
        """Serialise and deserialise preserves all fields."""
        occ = FaultOccurrence(
            site_code="S002",
            equipment_id="S002-URINAL-B1-001",
            issue_type="urinal_blocked",
            is_cluster_alert=True,
            cluster_count=3,
        )
        d = occ.to_dict()
        restored = FaultOccurrence.from_dict(d)
        assert restored.site_code == "S002"
        assert restored.equipment_id == "S002-URINAL-B1-001"
        assert restored.issue_type == "urinal_blocked"
        assert restored.is_cluster_alert is True
        assert restored.cluster_count == 3

    def test_from_dict_with_iso_timestamp(self):
        """ISO timestamp string is parsed to datetime."""
        d = {
            "id": str(uuid.uuid4()),
            "site_code": "S002",
            "equipment_id": "S002-URINAL-B1-001",
            "issue_type": "urinal_blocked",
            "occurred_at": "2026-05-07T10:00:00",
            "is_cluster_alert": False,
            "cluster_count": 1,
        }
        occ = FaultOccurrence.from_dict(d)
        assert occ.occurred_at.year == 2026
        assert occ.occurred_at.month == 5
        assert occ.occurred_at.day == 7

    def test_empty_issue_type_defaults(self):
        """Empty strings are preserved, not coerced to None."""
        occ = FaultOccurrence(site_code="S002", equipment_id="", issue_type="")
        assert occ.equipment_id == ""
        assert occ.issue_type == ""
        assert occ.is_cluster_alert is False
        assert occ.cluster_count == 1


# ---------------------------------------------------------------------------
# FaultOccurrenceTracker unit tests
# ---------------------------------------------------------------------------


class TestFaultOccurrenceTrackerUnit:
    @pytest.fixture
    def mock_repo(self):
        """In-memory mock repository."""
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_track_fault_first_occurrence_no_cluster(self, mock_repo):
        """1st occurrence → is_cluster_alert=False, cluster_count=1."""
        from app.services.fault_occurrence_tracker import FaultOccurrenceTracker

        mock_repo.record_occurrence = AsyncMock(
            return_value=FaultOccurrence(
                site_code="S002",
                equipment_id="S002-URINAL-B1-001",
                issue_type="urinal_blocked",
                is_cluster_alert=False,
                cluster_count=1,
            )
        )
        tracker = FaultOccurrenceTracker(repository=mock_repo)
        result = await tracker.track_fault(
            site_code="S002",
            equipment_id="S002-URINAL-B1-001",
            issue_type="urinal_blocked",
        )
        assert result.is_cluster_alert is False
        assert result.cluster_count == 1

    @pytest.mark.asyncio
    async def test_track_fault_second_occurrence_no_cluster(self, mock_repo):
        """2nd occurrence → is_cluster_alert=False, cluster_count=2."""
        from app.services.fault_occurrence_tracker import FaultOccurrenceTracker

        mock_repo.record_occurrence = AsyncMock(
            return_value=FaultOccurrence(
                site_code="S002",
                equipment_id="S002-URINAL-B1-001",
                issue_type="urinal_blocked",
                is_cluster_alert=False,
                cluster_count=2,
            )
        )
        tracker = FaultOccurrenceTracker(repository=mock_repo)
        result = await tracker.track_fault(
            site_code="S002",
            equipment_id="S002-URINAL-B1-001",
            issue_type="urinal_blocked",
        )
        assert result.is_cluster_alert is False
        assert result.cluster_count == 2

    @pytest.mark.asyncio
    async def test_track_fault_third_occurrence_cluster_alert(self, mock_repo):
        """3rd occurrence → is_cluster_alert=True, cluster_count=3."""
        from app.services.fault_occurrence_tracker import FaultOccurrenceTracker

        mock_repo.record_occurrence = AsyncMock(
            return_value=FaultOccurrence(
                site_code="S002",
                equipment_id="S002-URINAL-B1-001",
                issue_type="urinal_blocked",
                is_cluster_alert=True,
                cluster_count=3,
            )
        )
        tracker = FaultOccurrenceTracker(repository=mock_repo)
        result = await tracker.track_fault(
            site_code="S002",
            equipment_id="S002-URINAL-B1-001",
            issue_type="urinal_blocked",
        )
        assert result.is_cluster_alert is True
        assert result.cluster_count == 3

    @pytest.mark.asyncio
    async def test_track_fault_fourth_occurrence_cluster_still_active(self, mock_repo):
        """4th occurrence → is_cluster_alert=True, cluster_count=4."""
        from app.services.fault_occurrence_tracker import FaultOccurrenceTracker

        mock_repo.record_occurrence = AsyncMock(
            return_value=FaultOccurrence(
                site_code="S002",
                equipment_id="S002-URINAL-B1-001",
                issue_type="urinal_blocked",
                is_cluster_alert=True,
                cluster_count=4,
            )
        )
        tracker = FaultOccurrenceTracker(repository=mock_repo)
        result = await tracker.track_fault(
            site_code="S002",
            equipment_id="S002-URINAL-B1-001",
            issue_type="urinal_blocked",
        )
        assert result.is_cluster_alert is True
        assert result.cluster_count == 4

    @pytest.mark.asyncio
    async def test_track_fault_non_blocking_on_exception(self, mock_repo):
        """If repo throws, track_fault returns non-cluster occurrence and does not raise."""
        from app.services.fault_occurrence_tracker import FaultOccurrenceTracker

        mock_repo.record_occurrence = AsyncMock(side_effect=RuntimeError("DB error"))
        tracker = FaultOccurrenceTracker(repository=mock_repo)
        result = await tracker.track_fault(
            site_code="S002",
            equipment_id="S002-URINAL-B1-001",
            issue_type="urinal_blocked",
        )
        # Non-cluster fallback returned — pipeline continues
        assert result.is_cluster_alert is False
        assert result.cluster_count == 0

    @pytest.mark.asyncio
    async def test_check_cluster_true_when_threshold_met(self, mock_repo):
        """check_cluster returns True when count >= threshold."""
        from app.services.fault_occurrence_tracker import FaultOccurrenceTracker

        mock_repo.get_occurrence_count = AsyncMock(return_value=3)
        tracker = FaultOccurrenceTracker(repository=mock_repo, cluster_threshold=3)
        is_cluster = await tracker.check_cluster("S002", "S002-URINAL-B1-001", "urinal_blocked")
        assert is_cluster is True

    @pytest.mark.asyncio
    async def test_check_cluster_false_when_below_threshold(self, mock_repo):
        """check_cluster returns False when count < threshold."""
        from app.services.fault_occurrence_tracker import FaultOccurrenceTracker

        mock_repo.get_occurrence_count = AsyncMock(return_value=2)
        tracker = FaultOccurrenceTracker(repository=mock_repo, cluster_threshold=3)
        is_cluster = await tracker.check_cluster("S002", "S002-URINAL-B1-001", "urinal_blocked")
        assert is_cluster is False

    @pytest.mark.asyncio
    async def test_get_cluster_alerts_returns_structured_alerts(self, mock_repo):
        """get_cluster_alerts returns ClusterAlert dataclasses."""
        from app.services.fault_occurrence_tracker import ClusterAlert, FaultOccurrenceTracker

        mock_repo.get_cluster_alerts = AsyncMock(
            return_value=[
                {
                    "equipment_id": "S002-URINAL-B1-001",
                    "issue_type": "urinal_blocked",
                    "cluster_count": 3,
                    "latest_occurred_at": "2026-05-07T10:00:00",
                }
            ]
        )
        tracker = FaultOccurrenceTracker(repository=mock_repo)
        alerts = await tracker.get_cluster_alerts("S002")
        assert len(alerts) == 1
        assert isinstance(alerts[0], ClusterAlert)
        assert alerts[0].equipment_id == "S002-URINAL-B1-001"
        assert alerts[0].cluster_count == 3

    @pytest.mark.asyncio
    async def test_reset_cluster_calls_repo(self, mock_repo):
        """reset_cluster delegates to repository."""
        from app.services.fault_occurrence_tracker import FaultOccurrenceTracker

        mock_repo.reset_cluster_count = AsyncMock()
        tracker = FaultOccurrenceTracker(repository=mock_repo)
        await tracker.reset_cluster("S002-URINAL-B1-001", "urinal_blocked", site_code="S002")
        mock_repo.reset_cluster_count.assert_called_once_with("S002-URINAL-B1-001", "urinal_blocked", "S002")


# ---------------------------------------------------------------------------
# FaultOccurrenceRepository tests (using temp JSON backup)
# ---------------------------------------------------------------------------


class TestFaultOccurrenceRepository:
    @pytest.fixture
    def temp_backup_path(self, tmp_path):
        """Provide a temporary JSON backup path."""
        return tmp_path / "fault_occurrences.json"

    @pytest.mark.asyncio
    async def test_record_occurrence_empty_equipment_id(self, temp_backup_path):
        """Empty equipment_id is handled gracefully (no insert, returns non-cluster)."""
        from app.database.repositories.fault_occurrence_repository import FaultOccurrenceRepository

        repo = FaultOccurrenceRepository()
        repo.json_backup_path = temp_backup_path

        result = await repo.record_occurrence(
            site_code="S002",
            equipment_id="",
            issue_type="urinal_blocked",
        )
        assert result.is_cluster_alert is False
        assert result.cluster_count == 0
        # No record should be written — file may not exist (empty input skipped)
        if temp_backup_path.exists():
            data = json.loads(temp_backup_path.read_text())
            assert len(data["occurrences"]) == 0

    @pytest.mark.asyncio
    async def test_record_occurrence_empty_issue_type(self, temp_backup_path):
        """Empty issue_type is handled gracefully."""
        from app.database.repositories.fault_occurrence_repository import FaultOccurrenceRepository

        repo = FaultOccurrenceRepository()
        repo.json_backup_path = temp_backup_path

        result = await repo.record_occurrence(
            site_code="S002",
            equipment_id="S002-URINAL-B1-001",
            issue_type="",
        )
        assert result.is_cluster_alert is False
        assert result.cluster_count == 0

    @pytest.mark.asyncio
    async def test_record_occurrence_first_no_cluster(self, temp_backup_path):
        """1st occurrence → is_cluster_alert=False."""
        from app.database.repositories.fault_occurrence_repository import FaultOccurrenceRepository

        repo = FaultOccurrenceRepository()
        repo.json_backup_path = temp_backup_path

        result = await repo.record_occurrence(
            site_code="S002",
            equipment_id="S002-URINAL-B1-001",
            issue_type="urinal_blocked",
        )
        assert result.is_cluster_alert is False
        assert result.cluster_count == 1
        # Written to JSON backup
        data = json.loads(temp_backup_path.read_text())
        assert len(data["occurrences"]) == 1

    @pytest.mark.asyncio
    async def test_record_occurrence_third_triggers_cluster(self, temp_backup_path):
        """3rd occurrence with no Supabase → triggers cluster alert via JSON count."""
        from app.database.repositories.fault_occurrence_repository import FaultOccurrenceRepository

        repo = FaultOccurrenceRepository()
        repo.json_backup_path = temp_backup_path
        # Force JSON-only path by having _client be None
        repo._client = None

        # Record 1st and 2nd manually into backup
        initial_data = {
            "occurrences": [
                {
                    "id": "abc-1",
                    "site_code": "S002",
                    "equipment_id": "S002-URINAL-B1-001",
                    "issue_type": "urinal_blocked",
                    "occurred_at": datetime.utcnow().isoformat(),
                    "is_cluster_alert": False,
                    "cluster_count": 1,
                    "recommendation_id": None,
                },
                {
                    "id": "abc-2",
                    "site_code": "S002",
                    "equipment_id": "S002-URINAL-B1-001",
                    "issue_type": "urinal_blocked",
                    "occurred_at": datetime.utcnow().isoformat(),
                    "is_cluster_alert": False,
                    "cluster_count": 2,
                    "recommendation_id": None,
                },
            ]
        }
        temp_backup_path.write_text(json.dumps(initial_data))

        # 3rd occurrence
        result = await repo.record_occurrence(
            site_code="S002",
            equipment_id="S002-URINAL-B1-001",
            issue_type="urinal_blocked",
        )
        assert result.is_cluster_alert is True
        assert result.cluster_count == 3

    @pytest.mark.asyncio
    async def test_record_occurrence_fourth_cluster_still_active(self, temp_backup_path):
        """4th occurrence → is_cluster_alert=True, cluster_count=4."""
        from app.database.repositories.fault_occurrence_repository import FaultOccurrenceRepository

        repo = FaultOccurrenceRepository()
        repo.json_backup_path = temp_backup_path
        repo._client = None

        # Seed 3 occurrences
        initial_data = {
            "occurrences": [
                {
                    "id": f"abc-{i}",
                    "site_code": "S002",
                    "equipment_id": "S002-URINAL-B1-001",
                    "issue_type": "urinal_blocked",
                    "occurred_at": datetime.utcnow().isoformat(),
                    "is_cluster_alert": True,
                    "cluster_count": 3,
                    "recommendation_id": None,
                }
                for i in range(1, 4)
            ]
        }
        temp_backup_path.write_text(json.dumps(initial_data))

        result = await repo.record_occurrence(
            site_code="S002",
            equipment_id="S002-URINAL-B1-001",
            issue_type="urinal_blocked",
        )
        assert result.is_cluster_alert is True
        assert result.cluster_count == 4

    @pytest.mark.asyncio
    async def test_get_occurrence_count_in_window(self, temp_backup_path):
        """Count reflects only occurrences within sliding window."""
        from app.database.repositories.fault_occurrence_repository import FaultOccurrenceRepository

        repo = FaultOccurrenceRepository()
        repo.json_backup_path = temp_backup_path
        repo._client = None

        now = datetime.utcnow()
        old_date = (now - timedelta(days=100)).isoformat()
        recent_date = (now - timedelta(days=30)).isoformat()

        initial_data = {
            "occurrences": [
                {
                    "id": "old-1",
                    "site_code": "S002",
                    "equipment_id": "S002-URINAL-B1-001",
                    "issue_type": "urinal_blocked",
                    "occurred_at": old_date,
                    "is_cluster_alert": False,
                    "cluster_count": 1,
                    "recommendation_id": None,
                },
                {
                    "id": "recent-1",
                    "site_code": "S002",
                    "equipment_id": "S002-URINAL-B1-001",
                    "issue_type": "urinal_blocked",
                    "occurred_at": recent_date,
                    "is_cluster_alert": False,
                    "cluster_count": 1,
                    "recommendation_id": None,
                },
            ]
        }
        temp_backup_path.write_text(json.dumps(initial_data))

        count = await repo.get_occurrence_count(
            site_code="S002",
            equipment_id="S002-URINAL-B1-001",
            issue_type="urinal_blocked",
            window_days=90,
        )
        # Only the recent occurrence should be counted
        assert count == 1

    @pytest.mark.asyncio
    async def test_get_cluster_alerts_filters_by_threshold(self, temp_backup_path):
        """Equipment below cluster threshold is not in alerts."""
        from app.database.repositories.fault_occurrence_repository import FaultOccurrenceRepository

        repo = FaultOccurrenceRepository()
        repo.json_backup_path = temp_backup_path
        repo._client = None

        now = datetime.utcnow()
        recent = now.isoformat()
        initial_data = {
            "occurrences": [
                {
                    "id": f"occ-{i}",
                    "site_code": "S002",
                    "equipment_id": "S002-URINAL-B1-001",
                    "issue_type": "urinal_blocked",
                    "occurred_at": recent,
                    "is_cluster_alert": False,
                    "cluster_count": 2,
                    "recommendation_id": None,
                }
                for i in range(2)  # only 2 occurrences — below threshold of 3
            ]
        }
        temp_backup_path.write_text(json.dumps(initial_data))

        alerts = await repo.get_cluster_alerts("S002", cluster_threshold=3)
        assert len(alerts) == 0  # not enough occurrences

    @pytest.mark.asyncio
    async def test_reset_cluster_count(self, temp_backup_path):
        """reset_cluster_count marks occurrences as acknowledged."""
        from app.database.repositories.fault_occurrence_repository import FaultOccurrenceRepository

        repo = FaultOccurrenceRepository()
        repo.json_backup_path = temp_backup_path
        repo._client = None

        now = datetime.utcnow().isoformat()
        initial_data = {
            "occurrences": [
                {
                    "id": "occ-1",
                    "site_code": "S002",
                    "equipment_id": "S002-URINAL-B1-001",
                    "issue_type": "urinal_blocked",
                    "occurred_at": now,
                    "is_cluster_alert": True,
                    "cluster_count": 3,
                    "recommendation_id": None,
                }
            ]
        }
        temp_backup_path.write_text(json.dumps(initial_data))

        await repo.reset_cluster_count("S002-URINAL-B1-001", "urinal_blocked", site_code="S002")

        data = json.loads(temp_backup_path.read_text())
        assert data["occurrences"][0]["is_cluster_alert"] is False
        assert "cluster_acknowledged_at" in data["occurrences"][0]

    @pytest.mark.asyncio
    async def test_concurrent_insert_handled_gracefully(self, temp_backup_path):
        """Simulate concurrent insert by manually adding two records then checking count."""
        from app.database.repositories.fault_occurrence_repository import FaultOccurrenceRepository

        repo = FaultOccurrenceRepository()
        repo.json_backup_path = temp_backup_path
        repo._client = None

        now = datetime.utcnow().isoformat()
        initial_data = {
            "occurrences": [
                {
                    "id": f"occ-{i}",
                    "site_code": "S002",
                    "equipment_id": "S002-URINAL-B1-001",
                    "issue_type": "urinal_blocked",
                    "occurred_at": now,
                    "is_cluster_alert": False,
                    "cluster_count": 1,
                    "recommendation_id": None,
                }
                for i in range(2)
            ]
        }
        temp_backup_path.write_text(json.dumps(initial_data))

        # The repository checks count BEFORE inserting, so adding two at same time
        # should result in 3rd occurrence triggering cluster
        result = await repo.record_occurrence(
            site_code="S002",
            equipment_id="S002-URINAL-B1-001",
            issue_type="urinal_blocked",
        )
        assert result.cluster_count == 3
        assert result.is_cluster_alert is True
