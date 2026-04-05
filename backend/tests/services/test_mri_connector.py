"""
Unit tests for MRI Evolution Connector (Phase 178).

Tests cover:
    - Priority map coverage (all 9 MRI labels + None/empty fallback)
    - SLA breach detection (attend, respond, temp_fix)
    - Upsert deduplication (external_ref unique constraint)

All tests mock the Supabase client directly on the service instance.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, PropertyMock, patch
from uuid import uuid4

import pytest

from app.models.maintenance_event import MaintenanceEvent
from app.services.mri_connector_service import MRIConnectorService
from app.services.mri_priority_map import PRIORITY_MAP, normalise_priority

# ------------------------------------------------------------------
# Fixed reference "now" for deterministic SLA timing tests.
# All test timestamps are computed relative to this constant.
# ------------------------------------------------------------------
_FIXED_NOW = datetime(2026, 4, 5, 12, 0, 0, tzinfo=UTC)


# =============================================================================
# 1. Priority Map Coverage
# =============================================================================


class TestMRIPriorityMap:
    """Verify all MRI Evolution priority labels map to correct P1-P4 tiers."""

    @pytest.mark.parametrize(
        "label,expected_tier",
        [
            # P1 — Very Critical, URGENT, High
            ("Very Critical", "P1"),
            ("URGENT", "P1"),
            ("High", "P1"),
            # P2 — Critical
            ("Critical", "P2"),
            # P3 — Non Critical, Low, Medium
            ("Non Critical", "P3"),
            ("Low", "P3"),
            ("Medium", "P3"),
            # P4 — Routine, Planned
            ("Routine", "P4"),
            ("Planned", "P4"),
        ],
    )
    def test_known_labels_map_to_correct_tier(self, label, expected_tier):
        """All 9 documented MRI labels resolve to the expected P1-P4 tier."""
        result = normalise_priority(label)
        assert result["tier"] == expected_tier, f"{label} should map to {expected_tier}, got {result['tier']}"

    def test_very_critical_includes_respond_and_attend_hours(self):
        """P1 priority must carry 1hr respond + 4hr attend SLA targets."""
        result = normalise_priority("Very Critical")
        assert result["respond_hours"] == 1
        assert result["attend_hours"] == 4
        assert result["temp_fix_hours"] == 8
        assert result["resolve_work_days"] is None

    def test_critical_has_correct_p2_sla_hours(self):
        """P2 Critical must carry 2hr respond + 6hr attend SLA targets."""
        result = normalise_priority("Critical")
        assert result["tier"] == "P2"
        assert result["respond_hours"] == 2
        assert result["attend_hours"] == 6
        assert result["temp_fix_hours"] == 12
        assert result["resolve_work_days"] == 3

    def test_non_critical_has_correct_p3_sla_hours(self):
        """P3 Non Critical must carry 3hr respond + 8hr attend SLA targets."""
        result = normalise_priority("Non Critical")
        assert result["tier"] == "P3"
        assert result["respond_hours"] == 3
        assert result["attend_hours"] == 8
        assert result["temp_fix_hours"] == 16
        assert result["resolve_work_days"] == 6

    def test_routine_has_correct_p4_sla_hours(self):
        """P4 Routine must carry 4hr respond + 24hr attend SLA targets."""
        result = normalise_priority("Routine")
        assert result["tier"] == "P4"
        assert result["respond_hours"] == 4
        assert result["attend_hours"] == 24
        assert result["temp_fix_hours"] == 48
        assert result["resolve_work_days"] == 15

    def test_planned_also_maps_to_p4(self):
        """Planned label also maps to P4 with same SLA hours as Routine."""
        routine = normalise_priority("Routine")
        planned = normalise_priority("Planned")
        assert planned["tier"] == routine["tier"]
        assert planned["respond_hours"] == routine["respond_hours"]
        assert planned["attend_hours"] == routine["attend_hours"]

    def test_unknown_label_defaults_to_p4(self):
        """An undocumented MRI priority label must fall back to P4, not raise."""
        result = normalise_priority("SomeUnknownLabel")
        assert result["tier"] == "P4"

    @pytest.mark.parametrize("label", ["", "  ", "\t\n"])
    def test_empty_or_whitespace_label_defaults_to_p4(self, label):
        """None, empty string, or whitespace-only labels fall back to P4."""
        assert normalise_priority(label)["tier"] == "P4"

    def test_none_label_defaults_to_p4(self):
        """None priority falls back to P4."""
        assert normalise_priority(None)["tier"] == "P4"

    def test_all_nine_labels_covered_in_map(self):
        """Sanity check: PRIORITY_MAP has exactly 9 documented keys."""
        assert len(PRIORITY_MAP) == 9


# =============================================================================
# 2. SLA Breach Detection
# =============================================================================


def _make_event(
    external_ref: str = "FNBFW:30453",
    created_at_source: datetime | None = None,
    sla_respond_hours: int | None = 3,
    sla_attend_hours: int | None = 1,
    sla_temp_fix_hours: int | None = None,
    assigned_at: datetime | None = None,
    attended_at: datetime | None = None,
    temp_fixed_at: datetime | None = None,
    status: str = "Open",
) -> MaintenanceEvent:
    """Factory to build a MaintenanceEvent with sensible defaults."""
    return MaintenanceEvent(
        external_ref=external_ref,
        source_system="mri_evolution",
        site_id=None,
        priority_raw="High",
        priority_normalised="P1",
        sla_respond_hours=sla_respond_hours,
        sla_attend_hours=sla_attend_hours,
        sla_temp_fix_hours=sla_temp_fix_hours,
        created_at_source=created_at_source,
        assigned_at=assigned_at,
        attended_at=attended_at,
        temp_fixed_at=temp_fixed_at,
        status=status,
    )


def _mock_db_for_sla_breach(breach_event_id: str | None = None):
    """
    Build a mock Supabase client for SLA breach tests.

    The _check_sla_breach method:
      1. Looks up maintenance_event_id via select + maybe_single + execute
      2. Inserts breach record into sla_breach_events
    """
    mock_db = MagicMock()

    # Step 1 — select for maintenance_event_id lookup
    # Chain: table().select().eq().maybe_single().execute() -> response with data={"id": ...}
    mock_select_resp = MagicMock()
    event_id = breach_event_id or str(uuid4())
    type(mock_select_resp).data = PropertyMock(return_value={"id": event_id})
    mock_db.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = (
        mock_select_resp
    )

    # Step 2 — insert into sla_breach_events
    mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock()

    return mock_db


class TestSLABreachDetection:
    """Verify SLA breach detection writes correct records to sla_breach_events."""

    def test_attend_breach_detected_when_created_2h_ago_and_sla_1h(self):
        """Created 2h ago with sla_attend_hours=1 must record 1 attend breach.

        Relative to _FIXED_NOW=12:00:
          created_at = 10:00, sla_attend_hours=1 -> deadline = 11:00.
          attended_at = None -> compare_dt = _FIXED_NOW = 12:00 > 11:00 -> BREACH.
          sla_respond_hours=3 -> deadline = 13:00 > 12:00 -> no breach.
        """
        created_2h_ago = _FIXED_NOW - timedelta(hours=2)
        event = _make_event(
            created_at_source=created_2h_ago,
            sla_respond_hours=3,
            sla_attend_hours=1,
            assigned_at=None,
            attended_at=None,
        )

        mock_db = _mock_db_for_sla_breach()
        service = MRIConnectorService.__new__(MRIConnectorService)
        service.db = mock_db

        with patch("app.services.mri_connector_service.datetime") as mock_dt:
            mock_dt.now.return_value = _FIXED_NOW
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            service._check_sla_breach(event)

        insert_execute_calls = mock_db.table.return_value.insert.return_value.execute.call_args_list
        assert len(insert_execute_calls) == 1, f"Expected 1 breach insert, got {len(insert_execute_calls)}"

        breach_record = mock_db.table.return_value.insert.call_args[0][0]
        assert breach_record["breach_type"] == "attend"
        assert breach_record["sla_threshold_hours"] == 1

    def test_no_breach_when_attended_before_attend_deadline(self):
        """Attended at 10:30, deadline 11:00 -> 10:30 < 11:00, no breach.

        Relative to _FIXED_NOW=12:00:
          created_at = 08:00, sla_respond_hours=4, assigned_at = 08:00
            -> deadline = 12:00, compare_dt = 08:00 < 12:00 -> no respond breach.
          sla_attend_hours=1, attended_at = 09:30
            -> deadline = 09:00, compare_dt = 09:30 > 09:00 -> BREACH!

        To get no breach we need attended_at << deadline.
        Using attended_at = 08:00 + 0.5h = 08:30 with deadline 09:00:
          08:30 < 09:00 -> no breach.
        """
        created_4h_ago = _FIXED_NOW - timedelta(hours=4)
        event = _make_event(
            created_at_source=created_4h_ago,
            sla_respond_hours=4,  # deadline = 12:00 == _FIXED_NOW -> compare_dt(_FIXED_NOW - 4h) < deadline
            sla_attend_hours=1,  # deadline = 09:00
            assigned_at=_FIXED_NOW - timedelta(hours=4),  # 08:00 < deadline 12:00 -> no respond breach
            attended_at=_FIXED_NOW - timedelta(hours=3, minutes=30),  # 08:30 < deadline 09:00 -> no attend breach
        )

        mock_db = _mock_db_for_sla_breach()
        service = MRIConnectorService.__new__(MRIConnectorService)
        service.db = mock_db

        with patch("app.services.mri_connector_service.datetime") as mock_dt:
            mock_dt.now.return_value = _FIXED_NOW
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            service._check_sla_breach(event)

        insert_execute_calls = mock_db.table.return_value.insert.return_value.execute.call_args_list
        assert len(insert_execute_calls) == 0, f"No breach expected, got {len(insert_execute_calls)}"

    def test_respond_breach_detected_when_no_assignment_within_sla(self):
        """Created 4h ago, sla_respond_hours=1, not assigned -> respond breach only.

        Relative to _FIXED_NOW=12:00:
          created_at = 08:00, sla_respond_hours=1 -> deadline = 09:00.
          assigned_at = None -> compare_dt = _FIXED_NOW = 12:00 > 09:00 -> BREACH.
          sla_attend_hours=4 -> deadline = 12:00, compare_dt(_FIXED_NOW) not > deadline -> no attend breach.
        """
        created_4h_ago = _FIXED_NOW - timedelta(hours=4)
        event = _make_event(
            created_at_source=created_4h_ago,
            sla_respond_hours=1,
            sla_attend_hours=4,
            assigned_at=None,
            attended_at=None,
        )

        mock_db = _mock_db_for_sla_breach()
        service = MRIConnectorService.__new__(MRIConnectorService)
        service.db = mock_db

        with patch("app.services.mri_connector_service.datetime") as mock_dt:
            mock_dt.now.return_value = _FIXED_NOW
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            service._check_sla_breach(event)

        insert_execute_calls = mock_db.table.return_value.insert.return_value.execute.call_args_list
        assert len(insert_execute_calls) == 1, f"Expected 1 breach, got {len(insert_execute_calls)}"
        breach_record = mock_db.table.return_value.insert.call_args[0][0]
        assert breach_record["breach_type"] == "respond"

    def test_multiple_breach_types_recorded_together(self):
        """Both respond and attend breached -> two breach records written.

        Relative to _FIXED_NOW=12:00:
          created_at = 07:00
          respond: sla_respond_hours=1 -> deadline = 08:00, compare_dt = 12:00 > 08:00 -> BREACH.
          attend:  sla_attend_hours=2 -> deadline = 09:00, attended_at = 11:00 > 09:00 -> BREACH.
        """
        created_5h_ago = _FIXED_NOW - timedelta(hours=5)
        event = _make_event(
            created_at_source=created_5h_ago,
            sla_respond_hours=1,
            sla_attend_hours=2,
            assigned_at=None,
            attended_at=_FIXED_NOW - timedelta(hours=1),  # 11:00
        )

        mock_db = _mock_db_for_sla_breach()
        service = MRIConnectorService.__new__(MRIConnectorService)
        service.db = mock_db

        with patch("app.services.mri_connector_service.datetime") as mock_dt:
            mock_dt.now.return_value = _FIXED_NOW
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            service._check_sla_breach(event)

        insert_execute_calls = mock_db.table.return_value.insert.return_value.execute.call_args_list
        assert len(insert_execute_calls) == 2, f"Expected 2 breach inserts, got {len(insert_execute_calls)}"

        breach_types = {call[0][0]["breach_type"] for call in mock_db.table.return_value.insert.call_args_list}
        assert breach_types == {"respond", "attend"}

    def test_skip_breach_check_when_created_at_source_is_none(self):
        """Events without created_at_source must not query the DB at all."""
        event = _make_event(created_at_source=None)

        mock_db = _mock_db_for_sla_breach()
        service = MRIConnectorService.__new__(MRIConnectorService)
        service.db = mock_db

        service._check_sla_breach(event)

        # select (maintenance_events lookup) should never be called
        select_query = mock_db.table.return_value.select.return_value.eq.return_value
        select_calls = select_query.maybe_single.return_value.execute.call_args_list
        assert len(select_calls) == 0, "Should not query DB when created_at_source is None"


# =============================================================================
# 3. Upsert Deduplication
# =============================================================================


class TestUpsertDeduplication:
    """Verify upsert uses external_ref as unique key — UPDATE on match, INSERT on new."""

    def _build_upsert_mock(self, existing_data: list[dict] | None):
        """
        Build a mock Supabase client for _upsert tests.

        The _upsert method queries:
          table("maintenance_events").select("id").eq("external_ref", ...).execute()

        Uses PropertyMock on .data so that:
          - existing_data=None  -> existing.data is falsy (insert path)
          - existing_data=[{...}] -> existing.data is truthy (update path)
        """
        mock_db = MagicMock()

        # Build the chained call chain for upsert select query
        mock_execute = MagicMock()
        # PropertyMock on .data ensures truthiness reflects actual value, not MagicMock
        type(mock_execute).data = PropertyMock(return_value=existing_data)
        mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_execute

        # Stub update and insert chains
        mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock()
        mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock()

        return mock_db

    def test_insert_new_event_when_external_ref_not_found(self):
        """A new external_ref triggers INSERT, not UPDATE."""
        event = _make_event(external_ref="FNBFW:99999", status="New")

        mock_db = self._build_upsert_mock(existing_data=None)
        service = MRIConnectorService.__new__(MRIConnectorService)
        service.db = mock_db

        result = service._upsert(event)

        assert result == "inserted"
        mock_db.table.return_value.insert.assert_called_once()
        mock_db.table.return_value.update.assert_not_called()

    def test_update_existing_event_when_external_ref_found(self):
        """An existing external_ref triggers UPDATE, not INSERT."""
        existing_id = str(uuid4())
        event = _make_event(external_ref="FNBFW:30453", status="In Progress")

        mock_db = self._build_upsert_mock(existing_data=[{"id": existing_id}])
        service = MRIConnectorService.__new__(MRIConnectorService)
        service.db = mock_db

        result = service._upsert(event)

        assert result == "updated"
        mock_db.table.return_value.update.assert_called_once()
        mock_db.table.return_value.insert.assert_not_called()

    def test_upsert_same_external_ref_different_status_only_one_record(self):
        """Re-upserting same external_ref with different status leaves exactly 1 record."""
        # First upsert — external_ref not in DB -> insert
        event_v1 = _make_event(external_ref="FNBFW:30453", status="Open")
        mock_db = self._build_upsert_mock(existing_data=None)
        service = MRIConnectorService.__new__(MRIConnectorService)
        service.db = mock_db

        result1 = service._upsert(event_v1)
        assert result1 == "inserted"
        assert mock_db.table.return_value.insert.call_count == 1

        # Second upsert — same external_ref already exists -> update
        event_v2 = _make_event(external_ref="FNBFW:30453", status="In Progress")
        existing_id = str(uuid4())
        mock_db2 = self._build_upsert_mock(existing_data=[{"id": existing_id}])
        service.db = mock_db2

        result2 = service._upsert(event_v2)
        assert result2 == "updated"
        assert mock_db2.table.return_value.update.call_count == 1

    def test_upsert_records_last_synced_at(self):
        """Insert path sets last_synced_at on the inserted record."""
        event = _make_event(external_ref="FNBFW:30453")

        mock_db = self._build_upsert_mock(existing_data=None)
        service = MRIConnectorService.__new__(MRIConnectorService)
        service.db = mock_db

        service._upsert(event)

        insert_call_args = mock_db.table.return_value.insert.call_args[0][0]
        assert "last_synced_at" in insert_call_args
        assert isinstance(insert_call_args["last_synced_at"], str)
        assert insert_call_args["last_synced_at"] != ""
