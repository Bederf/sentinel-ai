"""Tests for Indoor Air Quality Intelligence Service."""

import pytest

from app.services.iaq_service import (
    IAQService,
    _generate_alerts,
    _score_co2,
    _score_humidity,
    _score_pm25,
    _score_status,
    _score_temperature,
    _score_voc,
    score_zone,
)


def _make_zone(**overrides):
    defaults = {
        "zone_id": "Zone-001",
        "zone_name": "L0 North",
        "floor": "L0",
        "site_id": "site-002",
        "setpoint": 22.0,
        "current_temp": 22.5,
        "humidity": 45.0,
        "co2_ppm": 500,
        "typical_occupancy": 50,
        "area_sqm": 450,
    }
    defaults.update(overrides)
    return defaults


# ---------------------------------------------------------------------------
# Score status classification
# ---------------------------------------------------------------------------


class TestScoreStatus:
    def test_excellent(self):
        assert _score_status(95) == "excellent"
        assert _score_status(90) == "excellent"

    def test_good(self):
        assert _score_status(85) == "good"
        assert _score_status(70) == "good"

    def test_poor(self):
        assert _score_status(65) == "poor"
        assert _score_status(50) == "poor"

    def test_unhealthy(self):
        assert _score_status(49) == "unhealthy"
        assert _score_status(0) == "unhealthy"


# ---------------------------------------------------------------------------
# CO2 scoring
# ---------------------------------------------------------------------------


class TestCO2Scoring:
    def test_excellent_co2(self):
        score, _ = _score_co2(400)
        assert score == 100.0

    def test_good_co2(self):
        score, _ = _score_co2(700)
        assert 80 <= score < 100

    def test_warning_co2(self):
        score, _ = _score_co2(900)
        assert 50 <= score < 80

    def test_critical_co2(self):
        score, _ = _score_co2(1200)
        assert 20 <= score < 50

    def test_extreme_co2(self):
        score, _ = _score_co2(2000)
        assert score < 20

    def test_none_returns_default(self):
        score, info = _score_co2(None)
        assert score == 75.0
        assert "No sensor" in info


# ---------------------------------------------------------------------------
# Humidity scoring
# ---------------------------------------------------------------------------


class TestHumidityScoring:
    def test_optimal_humidity(self):
        score, _ = _score_humidity(47)
        assert score == 100.0

    def test_slightly_high(self):
        score, _ = _score_humidity(58)
        assert 50 < score < 100

    def test_warning_high(self):
        score, _ = _score_humidity(65)
        assert 20 <= score < 80

    def test_critical_high(self):
        score, _ = _score_humidity(75)
        assert score < 50

    def test_low_humidity(self):
        score, _ = _score_humidity(25)
        assert score < 80

    def test_none_returns_default(self):
        score, _ = _score_humidity(None)
        assert score == 75.0


# ---------------------------------------------------------------------------
# Temperature scoring
# ---------------------------------------------------------------------------


class TestTemperatureScoring:
    def test_perfect_match(self):
        score, _ = _score_temperature(22.0, 22.0)
        assert score == 100.0

    def test_small_deviation(self):
        score, _ = _score_temperature(22.3, 22.0)
        assert score >= 90

    def test_warning_deviation(self):
        score, _ = _score_temperature(24.5, 22.0)
        assert 20 <= score < 80

    def test_critical_deviation(self):
        score, _ = _score_temperature(25.5, 22.0)
        assert score < 50

    def test_none_returns_default(self):
        score, _ = _score_temperature(None, 22.0)
        assert score == 75.0


# ---------------------------------------------------------------------------
# VOC scoring
# ---------------------------------------------------------------------------


class TestVOCScoring:
    def test_excellent_voc(self):
        score, _ = _score_voc(50)
        assert score == 100.0

    def test_none_returns_default(self):
        score, _ = _score_voc(None)
        assert score == 75.0

    def test_high_voc(self):
        score, _ = _score_voc(800)
        assert score < 40


# ---------------------------------------------------------------------------
# PM2.5 scoring
# ---------------------------------------------------------------------------


class TestPM25Scoring:
    def test_excellent_pm25(self):
        score, _ = _score_pm25(5)
        assert score == 100.0

    def test_none_returns_default(self):
        score, _ = _score_pm25(None)
        assert score == 75.0

    def test_high_pm25(self):
        score, _ = _score_pm25(40)
        assert score < 40


# ---------------------------------------------------------------------------
# Zone scoring
# ---------------------------------------------------------------------------


class TestZoneScoring:
    def test_healthy_zone(self):
        zone = _make_zone(co2_ppm=500, humidity=45, current_temp=22.3, setpoint=22.0)
        result = score_zone(zone)
        assert result.iaq_score >= 80
        assert result.status in ("excellent", "good")
        assert len(result.components) == 5

    def test_unhealthy_zone(self):
        zone = _make_zone(co2_ppm=1800, humidity=75, current_temp=27.0, setpoint=22.0)
        result = score_zone(zone)
        assert result.iaq_score < 50
        assert result.status == "unhealthy"

    def test_zone_preserves_metadata(self):
        zone = _make_zone(zone_id="Zone-101", zone_name="L1 East", floor="L1")
        result = score_zone(zone)
        assert result.zone_id == "Zone-101"
        assert result.zone_name == "L1 East"
        assert result.floor == "L1"

    def test_missing_sensors_get_default_score(self):
        zone = _make_zone(co2_ppm=None, humidity=None, current_temp=None, setpoint=None)
        result = score_zone(zone)
        assert result.iaq_score == 75.0  # all defaults

    def test_components_have_correct_weights(self):
        zone = _make_zone()
        result = score_zone(zone)
        weights = {c.component: c.weight for c in result.components}
        assert weights["co2"] == 0.30
        assert weights["humidity"] == 0.20
        assert weights["temperature"] == 0.25
        assert weights["voc"] == 0.15
        assert weights["pm25"] == 0.10


# ---------------------------------------------------------------------------
# Alert generation
# ---------------------------------------------------------------------------


class TestAlertGeneration:
    def test_no_alerts_healthy_zone(self):
        zone = _make_zone(co2_ppm=500, humidity=45, current_temp=22.3, setpoint=22.0)
        alerts = _generate_alerts(zone)
        assert len(alerts) == 0

    def test_co2_warning_alert(self):
        zone = _make_zone(co2_ppm=1100)
        alerts = _generate_alerts(zone)
        co2_alerts = [a for a in alerts if a.alert_type == "co2_high"]
        assert len(co2_alerts) == 1
        assert co2_alerts[0].severity == "warning"

    def test_co2_critical_alert(self):
        zone = _make_zone(co2_ppm=1600)
        alerts = _generate_alerts(zone)
        co2_alerts = [a for a in alerts if a.alert_type == "co2_high"]
        assert len(co2_alerts) == 1
        assert co2_alerts[0].severity == "critical"

    def test_humidity_high_warning(self):
        zone = _make_zone(humidity=65)
        alerts = _generate_alerts(zone)
        hum_alerts = [a for a in alerts if a.alert_type == "humidity_high"]
        assert len(hum_alerts) == 1
        assert hum_alerts[0].severity == "warning"

    def test_humidity_high_critical(self):
        zone = _make_zone(humidity=75)
        alerts = _generate_alerts(zone)
        hum_alerts = [a for a in alerts if a.alert_type == "humidity_high"]
        assert len(hum_alerts) == 1
        assert hum_alerts[0].severity == "critical"

    def test_humidity_low_critical(self):
        zone = _make_zone(humidity=15)
        alerts = _generate_alerts(zone)
        hum_alerts = [a for a in alerts if a.alert_type == "humidity_low"]
        assert len(hum_alerts) == 1
        assert hum_alerts[0].severity == "critical"

    def test_temp_deviation_warning(self):
        zone = _make_zone(current_temp=24.5, setpoint=22.0)
        alerts = _generate_alerts(zone)
        temp_alerts = [a for a in alerts if a.alert_type == "temp_deviation"]
        assert len(temp_alerts) == 1
        assert temp_alerts[0].severity == "warning"

    def test_temp_deviation_critical(self):
        zone = _make_zone(current_temp=26.0, setpoint=22.0)
        alerts = _generate_alerts(zone)
        temp_alerts = [a for a in alerts if a.alert_type == "temp_deviation"]
        assert len(temp_alerts) == 1
        assert temp_alerts[0].severity == "critical"

    def test_multiple_alerts(self):
        zone = _make_zone(co2_ppm=1600, humidity=75, current_temp=26.0, setpoint=22.0)
        alerts = _generate_alerts(zone)
        assert len(alerts) >= 3


# ---------------------------------------------------------------------------
# Service integration
# ---------------------------------------------------------------------------


class TestIAQService:
    def test_get_site_iaq_from_json(self):
        svc = IAQService()
        svc._zone_repo = None  # force JSON fallback
        overview = svc.get_site_iaq("site-002")
        assert overview.total_zones > 0
        assert 0 <= overview.avg_iaq_score <= 100
        assert (
            overview.zones_excellent + overview.zones_good + overview.zones_poor + overview.zones_unhealthy
            == overview.total_zones
        )

    def test_get_zone_iaq_from_json(self):
        svc = IAQService()
        svc._zone_repo = None
        result = svc.get_zone_iaq("site-002", "Zone-001")
        assert result is not None
        assert result.zone_id == "Zone-001"
        assert 0 <= result.iaq_score <= 100

    def test_get_zone_iaq_not_found(self):
        svc = IAQService()
        svc._zone_repo = None
        result = svc.get_zone_iaq("site-002", "Zone-999")
        assert result is None

    def test_get_alerts_from_json(self):
        svc = IAQService()
        svc._zone_repo = None
        alerts = svc.get_alerts("site-002")
        assert isinstance(alerts, list)

    def test_well_compliance_report(self):
        svc = IAQService()
        svc._zone_repo = None
        report = svc.get_compliance_report("site-002", "well")
        assert report.report_type == "well"
        assert report.site_id == "site-002"
        assert report.zones_compliant + report.zones_non_compliant > 0
        assert "avg_co2_ppm" in report.metrics

    def test_esg_compliance_report(self):
        svc = IAQService()
        svc._zone_repo = None
        report = svc.get_compliance_report("site-002", "esg")
        assert report.report_type == "esg"
        assert "total_zones" in report.metrics
        assert "active_alerts" in report.metrics

    def test_empty_site_returns_zero_zones(self):
        svc = IAQService()
        svc._zone_repo = None
        overview = svc.get_site_iaq("site-999")
        assert overview.total_zones == 0
        assert overview.avg_iaq_score == 0


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_iaq_zones_endpoint():
    from httpx import ASGITransport, AsyncClient

    from tests.conftest import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/iaq/zones/site-002")
    assert response.status_code == 200
    data = response.json()
    assert "zones" in data
    assert "avg_iaq_score" in data
    assert data["total_zones"] > 0


@pytest.mark.asyncio
async def test_iaq_zone_detail_endpoint():
    from httpx import ASGITransport, AsyncClient

    from tests.conftest import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/iaq/zones/site-002/Zone-001")
    assert response.status_code == 200
    data = response.json()
    assert data["zone_id"] == "Zone-001"
    assert "iaq_score" in data
    assert "components" in data


@pytest.mark.asyncio
async def test_iaq_zone_not_found():
    from httpx import ASGITransport, AsyncClient

    from tests.conftest import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/iaq/zones/site-002/Zone-999")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_iaq_alerts_endpoint():
    from httpx import ASGITransport, AsyncClient

    from tests.conftest import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/iaq/alerts/site-002")
    assert response.status_code == 200
    data = response.json()
    assert "alerts" in data
    assert "total_alerts" in data


@pytest.mark.asyncio
async def test_iaq_compliance_well():
    from httpx import ASGITransport, AsyncClient

    from tests.conftest import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/iaq/compliance/site-002?report_type=well")
    assert response.status_code == 200
    data = response.json()
    assert data["report_type"] == "well"


@pytest.mark.asyncio
async def test_iaq_compliance_esg():
    from httpx import ASGITransport, AsyncClient

    from tests.conftest import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/iaq/compliance/site-002?report_type=esg")
    assert response.status_code == 200
    data = response.json()
    assert data["report_type"] == "esg"


@pytest.mark.asyncio
async def test_iaq_compliance_invalid_type():
    from httpx import ASGITransport, AsyncClient

    from tests.conftest import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/iaq/compliance/site-002?report_type=invalid")
    assert response.status_code == 400
