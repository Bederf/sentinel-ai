"""Tests for CapEx Planning API endpoints (Phase 128)."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


class TestCapExAnalysisEndpoint:
    """Test GET /api/capex/analysis/{equipment_code}."""

    def test_analysis_concept_asset(self):
        """Analysis works for known Concept Evolution asset."""
        resp = client.get("/api/capex/analysis/GW-HVAC-CH-001")
        assert resp.status_code == 200
        data = resp.json()
        assert data["equipment_code"] == "GW-HVAC-CH-001"
        assert data["recommendation"] in ("replace", "repair", "monitor")
        assert "npv_replace_zar" in data
        assert "npv_repair_zar" in data

    def test_analysis_with_overrides(self):
        """Analysis accepts query parameter overrides."""
        resp = client.get(
            "/api/capex/analysis/S002-CHILLER-B1-001",
            params={
                "age_years": 15,
                "health_score": 35,
                "replacement_cost_zar": 1500000,
                "discount_rate": 0.12,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["replacement_cost_zar"] == 1500000
        assert data["discount_rate"] == 0.12

    def test_analysis_unknown_equipment_uses_defaults(self):
        """Unknown equipment code falls back to type defaults."""
        resp = client.get(
            "/api/capex/analysis/UNKNOWN-AHU-001",
            params={"age_years": 10, "health_score": 60},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["equipment_type"] == "ahu"

    def test_analysis_invalid_health_score(self):
        """Health score > 100 returns 422."""
        resp = client.get(
            "/api/capex/analysis/TEST-001",
            params={"health_score": 150},
        )
        assert resp.status_code == 422


class TestCapExPortfolioEndpoint:
    """Test GET /api/capex/portfolio/{site_id}."""

    def test_portfolio_returns_analysis(self):
        """Portfolio endpoint returns categorized equipment."""
        resp = client.get("/api/capex/portfolio/site-002")
        assert resp.status_code == 200
        data = resp.json()
        assert data["site_id"] == "site-002"
        assert "replace_candidates" in data
        assert "repair_candidates" in data
        assert "monitor_candidates" in data
        assert data["total_equipment"] > 0

    def test_portfolio_with_custom_horizon(self):
        """Portfolio accepts custom horizon."""
        resp = client.get(
            "/api/capex/portfolio/site-002",
            params={"horizon_years": 5},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["budget_forecast"]) == 5


class TestCapExBudgetForecastEndpoint:
    """Test GET /api/capex/budget-forecast/{site_id}."""

    def test_budget_forecast_returns_yearly(self):
        """Budget forecast returns yearly CapEx projections."""
        resp = client.get(
            "/api/capex/budget-forecast/site-002",
            params={"horizon_years": 5},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["horizon_years"] == 5
        assert len(data["budget_forecast"]) == 5
        assert "total_capex_needed_zar" in data


class TestCapExScenarioEndpoint:
    """Test POST /api/capex/scenario."""

    def test_scenario_analysis(self):
        """Scenario endpoint runs multiple what-if analyses."""
        resp = client.post(
            "/api/capex/scenario",
            json={
                "equipment_type": "chiller",
                "age_years": 20,
                "health_score": 35,
                "scenarios": [
                    {"name": "Base", "discount_rate": 0.10},
                    {"name": "High", "discount_rate": 0.20},
                ],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["scenario_count"] == 2
        assert "dominant_recommendation" in data

    def test_scenario_empty_list_rejected(self):
        """Empty scenario list returns 422."""
        resp = client.post(
            "/api/capex/scenario",
            json={
                "equipment_type": "chiller",
                "age_years": 10,
                "health_score": 50,
                "scenarios": [],
            },
        )
        assert resp.status_code == 422

    def test_scenario_too_many_rejected(self):
        """More than 10 scenarios returns 422."""
        resp = client.post(
            "/api/capex/scenario",
            json={
                "equipment_type": "chiller",
                "age_years": 10,
                "health_score": 50,
                "scenarios": [{"name": f"S{i}"} for i in range(11)],
            },
        )
        assert resp.status_code == 422


class TestCapExReferenceEndpoints:
    """Test reference data endpoints."""

    def test_type_financials(self):
        """Type financials endpoint returns equipment cost data."""
        resp = client.get("/api/capex/type-financials")
        assert resp.status_code == 200
        data = resp.json()
        assert "chiller" in data
        assert "_defaults" in data

    def test_concept_assets(self):
        """Concept assets endpoint returns CSV data."""
        resp = client.get("/api/capex/concept-assets")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) > 0
        assert "AssetCode" in data[0]
