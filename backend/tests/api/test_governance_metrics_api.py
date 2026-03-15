"""Tests for the governance metrics REST API endpoints.

Endpoints:
  GET /api/governance/quality-gate-rules
  GET /api/governance/drift-scores
  GET /api/governance/approval-latency
  GET /api/governance/cost-by-route
  GET /api/governance/popia-evidence
"""


class TestQualityGateRulesEndpoint:
    """GET /api/governance/quality-gate-rules"""

    def test_quality_gate_rules_endpoint(self, test_client):
        resp = test_client.get("/api/governance/quality-gate-rules")
        assert resp.status_code == 200
        body = resp.json()
        assert "rules" in body
        assert isinstance(body["rules"], list)

    def test_quality_gate_rules_structure(self, test_client):
        """Seed a counter value and verify it appears in response."""
        from app.api.metrics import sentinel_quality_gate_rule_evaluations_total

        sentinel_quality_gate_rule_evaluations_total.labels(rule_name="test_rule", status="pass").inc(5)

        resp = test_client.get("/api/governance/quality-gate-rules")
        assert resp.status_code == 200
        body = resp.json()
        rules = body["rules"]
        test_rules = [r for r in rules if r["rule_name"] == "test_rule"]
        assert len(test_rules) >= 1
        assert test_rules[0]["pass"] >= 5


class TestDriftScoresEndpoint:
    """GET /api/governance/drift-scores"""

    def test_drift_scores_endpoint(self, test_client):
        resp = test_client.get("/api/governance/drift-scores")
        assert resp.status_code == 200
        body = resp.json()
        assert "models" in body
        assert "alerts" in body
        assert isinstance(body["models"], list)
        assert isinstance(body["alerts"], list)

    def test_drift_scores_models_structure(self, test_client):
        resp = test_client.get("/api/governance/drift-scores")
        body = resp.json()
        for model in body["models"]:
            assert "model_id" in model
            assert "drift_score" in model
            assert "alert_level" in model


class TestApprovalLatencyEndpoint:
    """GET /api/governance/approval-latency"""

    def test_approval_latency_endpoint(self, test_client):
        resp = test_client.get("/api/governance/approval-latency")
        assert resp.status_code == 200
        body = resp.json()
        assert "percentiles" in body
        assert "total_approvals" in body
        assert "rejection_rate" in body

    def test_approval_latency_percentiles_structure(self, test_client):
        resp = test_client.get("/api/governance/approval-latency")
        body = resp.json()
        pctls = body["percentiles"]
        assert "p50" in pctls
        assert "p95" in pctls
        assert "p99" in pctls
        assert isinstance(pctls["p50"], (int, float))


class TestCostByRouteEndpoint:
    """GET /api/governance/cost-by-route"""

    def test_cost_by_route_endpoint(self, test_client):
        resp = test_client.get("/api/governance/cost-by-route")
        assert resp.status_code == 200
        body = resp.json()
        assert "routes" in body
        assert "total_tokens" in body
        assert "total_cost_zar" in body
        assert isinstance(body["routes"], list)

    def test_cost_by_route_seeded(self, test_client):
        """Seed token/cost counters and verify they appear."""
        from app.api.metrics import (
            sentinel_ai_tokens_by_route_total,
            sentinel_ai_cost_by_route_total,
        )

        sentinel_ai_tokens_by_route_total.labels(route="chat", site_id="site-002", provider="claude").inc(100)
        sentinel_ai_cost_by_route_total.labels(route="chat", site_id="site-002").inc(0.50)

        resp = test_client.get("/api/governance/cost-by-route")
        body = resp.json()
        chat_routes = [r for r in body["routes"] if r["route"] == "chat"]
        assert len(chat_routes) >= 1
        assert chat_routes[0]["tokens"] >= 100
        assert body["total_tokens"] >= 100


class TestPOPIAEvidenceEndpoint:
    """GET /api/governance/popia-evidence"""

    def test_popia_evidence_endpoint(self, test_client):
        resp = test_client.get("/api/governance/popia-evidence")
        assert resp.status_code == 200
        body = resp.json()
        assert "metadata" in body

    def test_popia_evidence_with_year_month_params(self, test_client):
        resp = test_client.get("/api/governance/popia-evidence?year=2026&month=1")
        assert resp.status_code == 200
        body = resp.json()
        assert "metadata" in body
        assert body["metadata"]["period"] == "2026-01"

    def test_popia_evidence_invalid_params(self, test_client):
        """Non-integer params should return 422."""
        resp = test_client.get("/api/governance/popia-evidence?year=abc")
        assert resp.status_code == 422
