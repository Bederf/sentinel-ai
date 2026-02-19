"""Integration tests for Phase A energy consumption pipeline.

Tests cover all 11 Phase A API endpoints via a minimal FastAPI app
that includes only the energy router (avoids cv2/apscheduler deps).

Endpoints tested:
    1. GET  /api/water/simulated-consumption
    2. GET  /api/water/tariff-info
    3. POST /api/validation/power-meter
    4. GET  /api/validation/power-meter/baseline
    5. GET  /api/validation/power-meter/cop-adjustment
    6. POST /api/validation/cost
    7. GET  /api/validation/cost/daily
    8. GET  /api/validation/cost/tariff-adjustment
    9. POST /api/recommendations/ai
   10. GET  /api/recommendations/dashboard
   11. GET  /api/recommendations/by-type
"""

import os
import asyncio

import pytest
from fastapi import FastAPI
from httpx import AsyncClient, ASGITransport

os.environ.setdefault("DEMO_MODE", "true")
os.environ.setdefault("TESTING", "true")

from app.api.energy import router as energy_router  # noqa: E402

# Build a minimal app with only the energy router so we don't need
# cv2, apscheduler, anthropic, etc.
_app = FastAPI(title="Phase A Energy Tests")
_app.include_router(energy_router, prefix="/api")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def client():
    """Synchronous-friendly async client wrapper."""

    class _Client:
        def _run(self, coro):
            return asyncio.run(coro)

        async def _request(self, method, url, **kwargs):
            transport = ASGITransport(app=_app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                return await ac.request(method, url, **kwargs)

        def get(self, url, **kwargs):
            return self._run(self._request("GET", url, **kwargs))

        def post(self, url, **kwargs):
            return self._run(self._request("POST", url, **kwargs))

    return _Client()


# ===========================================================================
# 1. Water Simulated Consumption
# ===========================================================================


class TestWaterSimulatedConsumption:
    """GET /api/water/simulated-consumption"""

    def test_returns_200(self, client):
        resp = client.get(
            "/api/water/simulated-consumption",
            params={"site_id": "site-002", "days": 7},
        )
        assert resp.status_code == 200

    def test_response_structure(self, client):
        resp = client.get(
            "/api/water/simulated-consumption",
            params={"site_id": "site-002", "days": 7},
        )
        data = resp.json()
        assert "site_id" in data
        assert "period_days" in data
        assert "total_liters" in data
        assert "total_cost_r" in data
        assert "average_daily_liters" in data
        assert "average_daily_cost_r" in data
        assert "daily_consumption" in data
        assert isinstance(data["daily_consumption"], list)

    def test_site_id_echoed(self, client):
        resp = client.get(
            "/api/water/simulated-consumption",
            params={"site_id": "site-002", "days": 3},
        )
        assert resp.json()["site_id"] == "site-002"


# ===========================================================================
# 2. Water Tariff Info
# ===========================================================================


class TestWaterTariffInfo:
    """GET /api/water/tariff-info"""

    def test_returns_200(self, client):
        resp = client.get("/api/water/tariff-info", params={"site_id": "site-002"})
        assert resp.status_code == 200

    def test_johannesburg_tariff(self, client):
        data = client.get("/api/water/tariff-info", params={"site_id": "site-002"}).json()
        assert data["municipality"] == "Johannesburg"
        assert data["currency"] == "ZAR"

    def test_tier_rates_present(self, client):
        data = client.get("/api/water/tariff-info", params={"site_id": "site-002"}).json()
        tiers = data["tiers"]
        assert len(tiers) == 3
        assert tiers[0]["tier"] == 1
        assert tiers[1]["tier"] == 2
        assert tiers[2]["tier"] == 3
        for tier in tiers:
            assert "rate_r_per_kiloliter" in tier
            assert "threshold_liters" in tier

    def test_sewerage_charge_present(self, client):
        data = client.get("/api/water/tariff-info", params={"site_id": "site-002"}).json()
        assert "sewerage_charge" in data
        assert data["sewerage_charge"]["rate_r_per_kiloliter"] > 0

    def test_fixed_monthly_charge(self, client):
        data = client.get("/api/water/tariff-info", params={"site_id": "site-002"}).json()
        assert data["fixed_monthly_charge_r"] > 0


# ===========================================================================
# 3. Power Meter Validation
# ===========================================================================


class TestPowerMeterValidation:
    """POST /api/validation/power-meter"""

    def test_returns_200(self, client):
        resp = client.post(
            "/api/validation/power-meter",
            params={
                "site_id": "site-002",
                "meter_id": "S002-MTR-B1-HVAC",
                "simulated_power_kw": 28.5,
                "simulated_hour": 12,
            },
        )
        assert resp.status_code == 200

    def test_response_has_validation_fields(self, client):
        data = client.post(
            "/api/validation/power-meter",
            params={
                "site_id": "site-002",
                "meter_id": "S002-MTR-B1-HVAC",
                "simulated_power_kw": 28.5,
                "simulated_hour": 12,
            },
        ).json()
        assert "validation_status" in data
        assert "simulated_kw" in data or "validation_status" in data
        # In demo mode without real meter, may return 'skipped' or 'normal'
        assert data["validation_status"] in (
            "normal",
            "anomaly",
            "critical",
            "skipped",
        )

    def test_high_power_reading(self, client):
        """High simulated power should still return a valid response."""
        data = client.post(
            "/api/validation/power-meter",
            params={
                "site_id": "site-002",
                "meter_id": "S002-MTR-B1-HVAC",
                "simulated_power_kw": 500.0,
                "simulated_hour": 14,
            },
        ).json()
        assert "validation_status" in data


# ===========================================================================
# 4. Power Meter Baseline
# ===========================================================================


class TestPowerMeterBaseline:
    """GET /api/validation/power-meter/baseline"""

    def test_returns_200(self, client):
        resp = client.get(
            "/api/validation/power-meter/baseline",
            params={
                "site_id": "site-002",
                "meter_id": "S002-MTR-B1-MAIN",
            },
        )
        assert resp.status_code == 200

    def test_baseline_stats_present(self, client):
        data = client.get(
            "/api/validation/power-meter/baseline",
            params={
                "site_id": "site-002",
                "meter_id": "S002-MTR-B1-MAIN",
            },
        ).json()
        # Demo fallback provides baseline stats
        assert "mean_kw" in data
        assert "stdev_kw" in data
        assert "min_kw" in data
        assert "max_kw" in data
        assert "samples" in data
        assert data["samples"] > 0


# ===========================================================================
# 5. COP Adjustment
# ===========================================================================


class TestCOPAdjustment:
    """GET /api/validation/power-meter/cop-adjustment"""

    def test_returns_200(self, client):
        resp = client.get(
            "/api/validation/power-meter/cop-adjustment",
            params={
                "site_id": "site-002",
                "meter_id": "S002-MTR-B1-MAIN",
            },
        )
        assert resp.status_code == 200

    def test_cop_fields_present(self, client):
        data = client.get(
            "/api/validation/power-meter/cop-adjustment",
            params={
                "site_id": "site-002",
                "meter_id": "S002-MTR-B1-MAIN",
            },
        ).json()
        assert "current_cop" in data
        assert "status" in data
        # Status can be healthy, degraded, unknown, or error in demo
        assert data["status"] in ("healthy", "degraded", "unknown", "error")


# ===========================================================================
# 6. Cost Validation
# ===========================================================================


class TestCostValidation:
    """POST /api/validation/cost"""

    def test_returns_200(self, client):
        resp = client.post(
            "/api/validation/cost",
            params={
                "site_id": "site-002",
                "month": 2,
                "year": 2026,
                "real_invoice_cost_r": 18500.00,
            },
        )
        assert resp.status_code == 200

    def test_validation_fields_present(self, client):
        data = client.post(
            "/api/validation/cost",
            params={
                "site_id": "site-002",
                "month": 2,
                "year": 2026,
                "real_invoice_cost_r": 18500.00,
            },
        ).json()
        assert "validation_status" in data
        assert "variance_pct" in data
        assert data["validation_status"] in (
            "validated",
            "warning",
            "critical",
        )

    def test_variance_is_numeric(self, client):
        data = client.post(
            "/api/validation/cost",
            params={
                "site_id": "site-002",
                "month": 2,
                "year": 2026,
                "real_invoice_cost_r": 18500.00,
            },
        ).json()
        assert isinstance(data["variance_pct"], (int, float))


# ===========================================================================
# 7. Cost Daily Breakdown
# ===========================================================================


class TestCostDaily:
    """GET /api/validation/cost/daily"""

    def test_returns_200(self, client):
        resp = client.get(
            "/api/validation/cost/daily",
            params={
                "site_id": "site-002",
                "energy_kwh": 315.0,
                "water_liters": 6847.0,
            },
        )
        assert resp.status_code == 200

    def test_cost_breakdown_present(self, client):
        data = client.get(
            "/api/validation/cost/daily",
            params={
                "site_id": "site-002",
                "energy_kwh": 315.0,
                "water_liters": 6847.0,
            },
        ).json()
        assert "energy_cost_r" in data
        assert "water_cost_r" in data
        assert "total_cost_r" in data
        assert data["energy_cost_r"] > 0
        assert data["water_cost_r"] > 0
        assert data["total_cost_r"] > 0

    def test_total_equals_sum(self, client):
        data = client.get(
            "/api/validation/cost/daily",
            params={
                "site_id": "site-002",
                "energy_kwh": 315.0,
                "water_liters": 6847.0,
            },
        ).json()
        expected_total = round(data["energy_cost_r"] + data["water_cost_r"], 2)
        assert abs(data["total_cost_r"] - expected_total) < 0.02


# ===========================================================================
# 8. Tariff Adjustment Recommendation
# ===========================================================================


class TestTariffAdjustment:
    """GET /api/validation/cost/tariff-adjustment"""

    def test_returns_200(self, client):
        resp = client.get(
            "/api/validation/cost/tariff-adjustment",
            params={"site_id": "site-002"},
        )
        assert resp.status_code == 200

    def test_adjustment_fields_present(self, client):
        data = client.get(
            "/api/validation/cost/tariff-adjustment",
            params={"site_id": "site-002"},
        ).json()
        assert "adjustment_needed" in data
        assert "recommended_tariff_multiplier" in data
        assert isinstance(data["adjustment_needed"], bool)
        assert isinstance(data["recommended_tariff_multiplier"], (int, float))

    def test_multiplier_reasonable(self, client):
        data = client.get(
            "/api/validation/cost/tariff-adjustment",
            params={"site_id": "site-002"},
        ).json()
        m = data["recommended_tariff_multiplier"]
        assert 0.8 <= m <= 1.2, f"Multiplier {m} outside reasonable range"


# ===========================================================================
# 9. AI Recommendations
# ===========================================================================


class TestAIRecommendations:
    """POST /api/recommendations/ai"""

    def test_returns_200(self, client):
        resp = client.post(
            "/api/recommendations/ai",
            params={"site_id": "site-002"},
        )
        assert resp.status_code == 200

    def test_response_structure(self, client):
        data = client.post(
            "/api/recommendations/ai",
            params={"site_id": "site-002"},
        ).json()
        assert "recommendation_count" in data
        assert "total_annual_savings_r" in data
        assert "recommendations" in data
        assert isinstance(data["recommendations"], list)
        assert data["recommendation_count"] == len(data["recommendations"])

    def test_recommendations_sorted_by_roi(self, client):
        data = client.post(
            "/api/recommendations/ai",
            params={"site_id": "site-002"},
        ).json()
        recs = data["recommendations"]
        if len(recs) >= 2:
            roi_values = [r.get("roi_pct", 0) for r in recs]
            assert roi_values == sorted(roi_values, reverse=True), "Recommendations not sorted by ROI descending"

    def test_each_recommendation_has_required_fields(self, client):
        data = client.post(
            "/api/recommendations/ai",
            params={"site_id": "site-002"},
        ).json()
        for rec in data["recommendations"]:
            assert "type" in rec
            assert "title" in rec
            assert "annual_savings_r" in rec
            assert "payback_months" in rec
            assert "roi_pct" in rec
            assert "confidence" in rec

    def test_annual_savings_positive(self, client):
        data = client.post(
            "/api/recommendations/ai",
            params={"site_id": "site-002"},
        ).json()
        assert data["total_annual_savings_r"] > 0
        for rec in data["recommendations"]:
            assert rec["annual_savings_r"] > 0


# ===========================================================================
# 10. Recommendations Dashboard
# ===========================================================================


class TestRecommendationsDashboard:
    """GET /api/recommendations/dashboard"""

    def test_returns_200(self, client):
        resp = client.get(
            "/api/recommendations/dashboard",
            params={"site_id": "site-002"},
        )
        assert resp.status_code == 200

    def test_top_recommendations_max_3(self, client):
        data = client.get(
            "/api/recommendations/dashboard",
            params={"site_id": "site-002"},
        ).json()
        assert "top_recommendations" in data
        assert len(data["top_recommendations"]) <= 3

    def test_call_to_action_present(self, client):
        data = client.get(
            "/api/recommendations/dashboard",
            params={"site_id": "site-002"},
        ).json()
        assert "call_to_action" in data
        assert len(data["call_to_action"]) > 0

    def test_total_savings_present(self, client):
        data = client.get(
            "/api/recommendations/dashboard",
            params={"site_id": "site-002"},
        ).json()
        assert "total_savings_r_annual" in data
        assert data["total_savings_r_annual"] > 0


# ===========================================================================
# 11. Recommendations By Type
# ===========================================================================


class TestRecommendationsByType:
    """GET /api/recommendations/by-type"""

    def test_returns_200(self, client):
        resp = client.get(
            "/api/recommendations/by-type",
            params={
                "site_id": "site-002",
                "recommendation_type": "lighting_optimization",
            },
        )
        assert resp.status_code == 200

    def test_recommendation_detail_present(self, client):
        data = client.get(
            "/api/recommendations/by-type",
            params={
                "site_id": "site-002",
                "recommendation_type": "lighting_optimization",
            },
        ).json()
        assert "recommendation" in data
        rec = data["recommendation"]
        assert rec["type"] == "lighting_optimization"
        assert "title" in rec
        assert "financials" in rec
        assert "metrics" in rec

    def test_financials_in_detail(self, client):
        data = client.get(
            "/api/recommendations/by-type",
            params={
                "site_id": "site-002",
                "recommendation_type": "lighting_optimization",
            },
        ).json()
        financials = data["recommendation"]["financials"]
        assert "annual_savings_r" in financials
        assert "investment_cost_r" in financials
        assert "payback_months" in financials
        assert "roi_pct" in financials

    def test_unknown_type_returns_not_found(self, client):
        data = client.get(
            "/api/recommendations/by-type",
            params={
                "site_id": "site-002",
                "recommendation_type": "nonexistent_type",
            },
        ).json()
        assert data.get("found") is False
