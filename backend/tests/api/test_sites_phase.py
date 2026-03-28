"""Tests for 173-01: Phase audit log write, GET field, and constraint.

Verifies:
  - PATCH /api/sites/{id}/phase writes a row to phase_transition_log
  - GET /api/sites/{id} includes last_phase_transition field
  - audit_log table accepts action='phase_transition' (no constraint violation)
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_fake_supabase(
    *,
    site_row: dict | None = None,
    phase_transition_row: dict | None = None,
) -> MagicMock:
    """Build a minimal fake Supabase client for sites/phase_transition_log calls."""

    class FakeQuery:
        def __init__(self, data=None):
            self._data = data or []

        def select(self, *_a, **_kw):
            return self

        def update(self, *_a, **_kw):
            return self

        def insert(self, *_a, **_kw):
            return self

        def eq(self, *_a, **_kw):
            return self

        def limit(self, *_a, **_kw):
            return self

        def order(self, *_a, **_kw):
            return self

        def execute(self):
            result = MagicMock()
            result.data = self._data
            return result

    site_data = [site_row] if site_row else []
    transition_data = [phase_transition_row] if phase_transition_row else []

    call_log: list[str] = []

    class FakeSupabase:
        def table(self, name: str):
            call_log.append(name)
            if name == "sites":
                q = FakeQuery(data=site_data)
            elif name == "phase_transition_log":
                q = FakeQuery(data=transition_data)
            else:
                q = FakeQuery()
            return q

        @property
        def tables_accessed(self):
            return call_log

    return FakeSupabase()  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Task 3a: PATCH writes to phase_transition_log
# ---------------------------------------------------------------------------


class TestPhaseTransitionLogWrittenOnPatch:
    """PATCH /api/sites/{id}/phase writes to phase_transition_log."""

    @pytest.mark.asyncio
    async def test_patch_phase_calls_phase_transition_log(self, monkeypatch, tmp_path):
        from app.api import sites as sites_api

        inserted_rows: list[dict] = []

        class CapturingQuery:
            def __init__(self):
                self._is_log_table = False

            def select(self, *_a, **_kw):
                return self

            def update(self, *_a, **_kw):
                return self

            def insert(self, payload: dict):
                if self._is_log_table:
                    inserted_rows.append(payload)
                return self

            def eq(self, *_a, **_kw):
                return self

            def limit(self, *_a, **_kw):
                return self

            def execute(self):
                result = MagicMock()
                result.data = [{"onboarding_phase": "shadow"}]
                return result

        class FakeSupabase:
            def table(self, name: str):
                q = CapturingQuery()
                if name == "phase_transition_log":
                    q._is_log_table = True
                return q

        monkeypatch.setattr(
            "app.database.supabase_client.get_supabase_client",
            lambda: FakeSupabase(),
        )

        data_dir = tmp_path / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(sites_api, "DATA_DIR", data_dir)
        monkeypatch.setattr(sites_api, "_ONBOARDING_PHASE_FILE", data_dir / "phase.json")
        monkeypatch.setattr(sites_api.settings, "use_json_storage", False)

        request = sites_api.PhaseUpdateRequest(
            phase="advisory",
            changed_by="admin@sentinel.local",
            reason="Initial rollout",
        )
        response = await sites_api.update_site_phase("S001", request)

        assert response.onboarding_phase == "advisory"
        assert response.site_id == "S001"
        # The phase_transition_log insert must have been attempted
        assert len(inserted_rows) == 1
        row = inserted_rows[0]
        assert row["to_phase"] == "advisory"
        assert row["changed_by"] == "admin@sentinel.local"
        assert row["reason"] == "Initial rollout"
        assert row["site_id"] == "S001"


# ---------------------------------------------------------------------------
# Task 3b: GET site includes last_phase_transition field
# ---------------------------------------------------------------------------


class TestSiteDetailIncludesLastPhaseTransition:
    """GET /api/sites/{id} response model includes last_phase_transition."""

    def test_site_response_model_has_last_phase_transition_field(self):
        from app.api.sites import SiteResponse

        fields = SiteResponse.model_fields
        assert "last_phase_transition" in fields

    def test_site_response_last_phase_transition_is_optional(self):
        """last_phase_transition is Optional — defaults to None."""
        from app.api.sites import SiteResponse

        resp = SiteResponse(
            id="site-001",
            name="Test Site",
            region="Gauteng",
            type="office",
            equipment_count=0,
            alert_count=0,
            location="Test Location",
            status="normal",
        )
        assert resp.last_phase_transition is None

    def test_site_response_last_phase_transition_carries_data(self):
        """last_phase_transition dict is preserved when provided."""
        from app.api.sites import SiteResponse

        transition = {
            "to_phase": "advisory",
            "changed_by": "admin@sentinel.local",
            "created_at": "2026-03-27T10:00:00+00:00",
            "reason": "Test",
        }
        resp = SiteResponse(
            id="site-001",
            name="Test Site",
            region="Gauteng",
            type="office",
            equipment_count=0,
            alert_count=0,
            location="Test Location",
            status="normal",
            last_phase_transition=transition,
        )
        assert resp.last_phase_transition == transition
        assert resp.last_phase_transition["to_phase"] == "advisory"  # type: ignore[index]


# ---------------------------------------------------------------------------
# Task 3c: audit_log action='phase_transition' is a valid action value
# ---------------------------------------------------------------------------


class TestAuditLogPhaseTransitionAction:
    """Migration 117 adds 'phase_transition' to audit_log.action CHECK constraint."""

    def test_migration_117_includes_phase_transition_action(self):
        """Verify migration SQL explicitly allows 'phase_transition' in audit_log."""
        from pathlib import Path

        migration_file = (
            Path(__file__).parent.parent.parent.parent / "supabase" / "migrations" / "117_phase_transition_log.sql"
        )
        assert migration_file.exists(), "Migration 117_phase_transition_log.sql must exist"
        sql = migration_file.read_text()
        assert "'phase_transition'" in sql, "audit_log CHECK constraint must include 'phase_transition'"
        assert "audit_log_action_check" in sql, "Constraint must be named audit_log_action_check"

    def test_migration_117_creates_phase_transition_log_table(self):
        """Verify migration creates the phase_transition_log table."""
        from pathlib import Path

        migration_file = (
            Path(__file__).parent.parent.parent.parent / "supabase" / "migrations" / "117_phase_transition_log.sql"
        )
        sql = migration_file.read_text()
        assert "CREATE TABLE IF NOT EXISTS phase_transition_log" in sql
        assert "site_id" in sql
        assert "from_phase" in sql
        assert "to_phase" in sql
        assert "changed_by" in sql
