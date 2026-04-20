"""Recommendation repository write-shape tests."""

import pytest

from app.database.repositories.recommendation_repository import RecommendationRepository


def test_filter_supabase_payload_drops_model_only_fields():
    """Supabase writes should not include fields absent from the live table."""
    repo = RecommendationRepository()

    payload = repo._filter_supabase_payload(
        {
            "id": "rec-1",
            "site_id": "S001",
            "status": "pending",
            "action_type": "setpoint_change",
            "source": "health_alert",
            "source_type": "rule_based",
            "correlation_id": "corr-1",
            "outcome_validated": True,
            "outcome_notes": "validated",
            "reason": "Test recommendation",
        }
    )

    assert payload["id"] == "rec-1"
    assert payload["site_id"] == "S001"
    assert payload["status"] == "pending"
    assert payload["action_type"] == "setpoint_change"
    assert payload["reason"] == "Test recommendation"
    assert "source" not in payload
    assert "source_type" not in payload
    assert "correlation_id" not in payload
    assert "outcome_validated" not in payload
    assert "outcome_notes" not in payload


@pytest.mark.asyncio
async def test_resolve_id_prefix_returns_single_db_match():
    """Short tokens should resolve from the canonical DB-backed recommendation set."""
    repo = RecommendationRepository()

    class _Resp:
        data = [
            {"id": "abc12345-0000-0000-0000-000000000000", "timestamp": "2026-03-16T10:00:00Z"},
            {"id": "def67890-0000-0000-0000-000000000000", "timestamp": "2026-03-16T09:00:00Z"},
        ]

    class _Query:
        def select(self, *_args, **_kwargs):
            return self

        def order(self, *_args, **_kwargs):
            return self

        def limit(self, *_args, **_kwargs):
            return self

        def execute(self):
            return _Resp()

    class _Client:
        def table(self, _name):
            return _Query()

    repo._client = _Client()

    resolved = await repo.resolve_id_prefix("abc12345")
    assert resolved == "abc12345-0000-0000-0000-000000000000"
