"""Tests for site-scoped AI policy and ML readiness gating."""

import pytest


@pytest.mark.asyncio
async def test_ml_training_enable_rejected_until_site_is_ready(client, auth_headers_admin, monkeypatch):
    """Admins cannot enable site ML training before telemetry readiness passes."""

    async def _not_ready(_site_id):
        return {"ready": False, "blocking_metrics": ["freshness_minutes", "match_coverage_pct"]}

    monkeypatch.setattr(
        "app.api.settings.get_site_ai_policy",
        lambda _site_id: {
            "chat_local_ai_only": False,
            "allow_tool_calling": True,
            "show_recommendations_in_shadow": False,
            "ml_training_enabled": False,
            "monthly_budget_zar": 0.0,
            "hard_cap_enforced": False,
        },
    )
    monkeypatch.setattr("app.services.site_ai_policy_service.get_ml_training_readiness", _not_ready)
    monkeypatch.setattr("app.api.settings.set_site_ai_policy", lambda *_args, **_kwargs: {"ml_training_enabled": True})
    monkeypatch.setattr("app.api.settings.audit_config_change", lambda *args, **kwargs: None)

    resp = await client.put(
        "/api/settings/ai-policy/site-005",
        headers=auth_headers_admin,
        json={"ml_training_enabled": True},
    )

    assert resp.status_code == 400
    body = resp.json()
    assert body["detail"]["error"] == "ml_training_not_ready"
    assert body["detail"]["readiness"]["ready"] is False


@pytest.mark.asyncio
async def test_ml_training_disable_still_allows_policy_update(client, auth_headers_admin, monkeypatch):
    """Admins can always disable site ML training."""

    async def _not_ready(_site_id):
        return {"ready": False}

    stored_policy = {
        "chat_local_ai_only": False,
        "allow_tool_calling": True,
        "show_recommendations_in_shadow": False,
        "ml_training_enabled": False,
        "monthly_budget_zar": 0.0,
        "hard_cap_enforced": False,
    }

    monkeypatch.setattr(
        "app.api.settings.get_site_ai_policy", lambda _site_id: {**stored_policy, "ml_training_enabled": True}
    )
    monkeypatch.setattr("app.services.site_ai_policy_service.get_ml_training_readiness", _not_ready)
    monkeypatch.setattr("app.api.settings.set_site_ai_policy", lambda _site_id, policy: policy)
    monkeypatch.setattr("app.api.settings.audit_config_change", lambda *args, **kwargs: None)

    resp = await client.put(
        "/api/settings/ai-policy/site-005",
        headers=auth_headers_admin,
        json={"ml_training_enabled": False},
    )

    assert resp.status_code == 200
    assert resp.json()["ml_training_enabled"] is False
