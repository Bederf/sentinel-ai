"""Tests for Demand Response Service.

Test scenarios:
1. Happy path — site-002, full live data, returns valid response
2. Zone at comfort boundary — headroom < 1.0°C, curtailable_kw = 0 for that zone
3. BESS not present — bess_soc_pct = null, ddmp_eligible still calculated correctly
4. BESS low SOC — limiting_factor = "bess_low_soc"
5. Stale data — last reading > 300s ago, returns 503
6. Site not found — returns 404
7. All zones P1/P2 only — curtailable_load_kw = 0.0
8. Confidence calculation — verify weighted average formula
9. DDMP eligibility — verify 500kW threshold and 60-minute duration rules
10. min_priority parameter — verify filtering works correctly
"""

from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.models.demand_response_models import CurtailableLoadResponse
from app.services.demand_response_service import DemandResponseService


@pytest.fixture
def dr_service():
    """Create a fresh demand response service instance."""
    return DemandResponseService()


@pytest.fixture
def mock_site():
    """Mock site data."""
    return {
        "id": "test-site-uuid",
        "code": "site-002",
        "name": "Test Site",
    }


@pytest.fixture
def mock_zones():
    """Mock zones with various priorities."""
    return [
        {"id": "zone-p1", "name": "Server Room", "priority": 1, "equipment_count": 2},
        {"id": "zone-p2", "name": "Executive Office", "priority": 2, "equipment_count": 3},
        {
            "id": "zone-p3",
            "name": "Open Office A",
            "priority": 3,
            "current_temp_c": 21.5,
            "setpoint_c": 22.0,
            "equipment_count": 5,
        },
        {
            "id": "zone-p4",
            "name": "Lobby",
            "priority": 4,
            "current_temp_c": 22.5,
            "setpoint_c": 22.0,
            "equipment_count": 2,
        },
        {
            "id": "zone-p5",
            "name": "Parking",
            "priority": 5,
            "current_temp_c": 23.0,
            "setpoint_c": 22.0,
            "equipment_count": 1,
        },
    ]


class TestDemandResponseService:
    """Test suite for DemandResponseService."""

    @pytest.mark.asyncio
    async def test_happy_path_full_response(self, dr_service, mock_site, mock_zones):
        """Test 1: Happy path returns valid response with all fields."""
        # Arrange
        with (
            patch.object(dr_service, "_get_site", return_value=mock_site),
            patch.object(dr_service, "_get_thermal_runway", return_value=95),
            patch.object(dr_service, "_get_power_summary", return_value={"hvac_kw": 200.0}),
            patch.object(dr_service, "_get_zones", return_value=mock_zones),
            patch.object(dr_service, "_get_zone_hvac_load", return_value=40.0),
            patch.object(dr_service, "_get_bess_soc", return_value=78.4),
            patch.object(dr_service, "_get_data_freshness_seconds", return_value=45),
        ):
            # Act
            response = await dr_service.get_curtailable_load("site-002", min_priority=3, include_zones=True)

            # Assert
            assert isinstance(response, CurtailableLoadResponse)
            assert response.site_id == "site-002"
            assert response.curtailable_load_kw > 0
            assert response.safe_duration_minutes == 95
            assert 0 <= response.confidence <= 0.95
            assert response.limiting_factor in [
                "chiller_thermal_mass",
                "comfort_boundary",
                "bess_low_soc",
                "zone_temperature_limit",
                "thermal_runway_short",
                "none",
            ]
            assert isinstance(response.is_load_shedding_active, bool)
            assert isinstance(response.ddmp_eligible, bool)
            assert response.bess_soc_pct == 78.4
            assert len(response.zone_breakdown) > 0
            assert response.data_freshness_seconds == 45

    @pytest.mark.asyncio
    async def test_zone_at_comfort_boundary_no_curtailment(self, dr_service, mock_site):
        """Test 2: Zone at comfort boundary (headroom < 1.0) has curtailable_kw = 0."""
        # Arrange - zone with 0.5°C headroom
        zones_with_boundary = [
            {
                "id": "zone-boundary",
                "name": "Boundary Zone",
                "priority": 3,
                "current_temp_c": 22.5,
                "setpoint_c": 22.0,
                "equipment_count": 3,
            },
        ]

        with (
            patch.object(dr_service, "_get_site", return_value=mock_site),
            patch.object(dr_service, "_get_thermal_runway", return_value=60),
            patch.object(dr_service, "_get_power_summary", return_value={"hvac_kw": 100.0}),
            patch.object(dr_service, "_get_zones", return_value=zones_with_boundary),
            patch.object(dr_service, "_get_zone_hvac_load", return_value=50.0),
            patch.object(dr_service, "_get_bess_soc", return_value=50.0),
            patch.object(dr_service, "_get_data_freshness_seconds", return_value=30),
        ):
            # Act
            response = await dr_service.get_curtailable_load("site-002", min_priority=3, include_zones=True)

            # Assert - boundary zone should have 0 curtailable load
            boundary_zone = next((z for z in response.zone_breakdown if z.zone_id == "zone-boundary"), None)
            assert boundary_zone is not None
            assert boundary_zone.curtailable_kw == 0.0
            assert boundary_zone.headroom_c == 0.5

    @pytest.mark.asyncio
    async def test_bess_not_present_null_soc(self, dr_service, mock_site, mock_zones):
        """Test 3: BESS not present returns null SOC but valid response."""
        with (
            patch.object(dr_service, "_get_site", return_value=mock_site),
            patch.object(dr_service, "_get_thermal_runway", return_value=80),
            patch.object(dr_service, "_get_power_summary", return_value={"hvac_kw": 150.0}),
            patch.object(dr_service, "_get_zones", return_value=mock_zones),
            patch.object(dr_service, "_get_zone_hvac_load", return_value=30.0),
            patch.object(dr_service, "_get_bess_soc", return_value=None),
            patch.object(dr_service, "_get_data_freshness_seconds", return_value=60),
        ):
            # Act
            response = await dr_service.get_curtailable_load("site-002")

            # Assert
            assert response.bess_soc_pct is None
            assert response.limiting_factor != "bess_low_soc"
            # DDMP eligibility should be calculated without BESS constraint
            assert isinstance(response.ddmp_eligible, bool)

    @pytest.mark.asyncio
    async def test_bess_low_soc_limiting_factor(self, dr_service, mock_site, mock_zones):
        """Test 4: BESS low SOC (< 20%) returns limiting_factor = 'bess_low_soc' when no comfort boundary issues."""
        # Create zones with good headroom (> 2.0°C)
        zones_good_headroom = [
            {
                "id": "zone-p3",
                "name": "Open Office",
                "priority": 3,
                "current_temp_c": 20.0,
                "setpoint_c": 22.0,
                "equipment_count": 5,
            },
        ]

        with (
            patch.object(dr_service, "_get_site", return_value=mock_site),
            patch.object(dr_service, "_get_thermal_runway", return_value=90),
            patch.object(dr_service, "_get_power_summary", return_value={"hvac_kw": 600.0}),
            patch.object(dr_service, "_get_zones", return_value=zones_good_headroom),
            patch.object(dr_service, "_get_zone_hvac_load", return_value=120.0),
            patch.object(dr_service, "_get_bess_soc", return_value=15.0),
            patch.object(dr_service, "_get_data_freshness_seconds", return_value=30),
        ):
            # Act
            response = await dr_service.get_curtailable_load("site-002")

            # Assert - BESS low SOC is limiting factor when headroom is good
            assert response.bess_soc_pct == 15.0
            assert response.limiting_factor == "bess_low_soc"

    @pytest.mark.asyncio
    async def test_stale_data_returns_503(self, dr_service, mock_site):
        """Test 5: Stale data (> 300s) returns HTTP 503."""
        with (
            patch.object(dr_service, "_get_site", return_value=mock_site),
            patch.object(dr_service, "_get_data_freshness_seconds", return_value=312),
        ):
            # Act & Assert
            with pytest.raises(HTTPException) as exc_info:
                await dr_service.get_curtailable_load("site-002")

            assert exc_info.value.status_code == 503
            assert "Insufficient live sensor data" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_site_not_found_returns_404(self, dr_service):
        """Test 6: Site not found returns HTTP 404."""
        with patch.object(dr_service, "_get_site", return_value=None):
            # Act & Assert
            with pytest.raises(HTTPException) as exc_info:
                await dr_service.get_curtailable_load("nonexistent-site")

            assert exc_info.value.status_code == 404
            assert "not found" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_all_zones_p1_p2_only_reduced_curtailment(self, dr_service, mock_site):
        """Test 7: All zones P1/P2 results in reduced curtailment (P1=0%, P2=50%)."""
        # Arrange - only P1 and P2 zones
        high_priority_zones = [
            {"id": "zone-p1", "name": "Server Room", "priority": 1, "equipment_count": 2},
            {"id": "zone-p2", "name": "Executive", "priority": 2, "equipment_count": 3},
        ]

        with (
            patch.object(dr_service, "_get_site", return_value=mock_site),
            patch.object(dr_service, "_get_thermal_runway", return_value=60),
            patch.object(dr_service, "_get_power_summary", return_value={"hvac_kw": 100.0}),
            patch.object(dr_service, "_get_zones", return_value=high_priority_zones),
            patch.object(dr_service, "_get_zone_hvac_load", return_value=50.0),
            patch.object(dr_service, "_get_bess_soc", return_value=50.0),
            patch.object(dr_service, "_get_data_freshness_seconds", return_value=30),
        ):
            # Act - request includes P1 and P2 zones
            response = await dr_service.get_curtailable_load("site-002", min_priority=1)

            # Assert - P1 contributes 0%, P2 contributes 50% of its load
            # With no temp data, default is 50% curtailment, so P2: 50 * 0.5 * 0.5 = 12.5
            p1_zone = next((z for z in response.zone_breakdown if z.zone_id == "zone-p1"), None)
            p2_zone = next((z for z in response.zone_breakdown if z.zone_id == "zone-p2"), None)

            assert p1_zone is not None
            assert p1_zone.curtailable_kw == 0.0  # P1 never curtailed
            assert p2_zone is not None
            assert p2_zone.curtailable_kw > 0  # P2 gets partial curtailment
            assert response.curtailable_load_kw > 0  # Total from P2 only

    def test_confidence_calculation_formula(self, dr_service):
        """Test 8: Confidence is weighted average with correct formula."""
        # Test data freshness scores
        test_cases = [
            # (freshness, coverage, thermal_confidence, expected_range)
            (30, 1.0, 0.9, (0.7, 0.95)),  # Fresh, full coverage, high thermal
            (90, 0.8, 0.85, (0.5, 0.9)),  # Moderate freshness
            (180, 0.5, 0.8, (0.3, 0.8)),  # Stale, partial coverage
            (400, 0.3, 0.7, (0.0, 0.5)),  # Very stale
        ]

        for freshness, coverage, thermal, expected_range in test_cases:
            confidence = dr_service._calculate_confidence(
                data_freshness_seconds=freshness,
                zones_with_live_data=int(coverage * 10),
                total_zones=10,
                thermal_runway_confidence=thermal,
            )
            assert 0.0 <= confidence <= 0.95
            assert expected_range[0] <= confidence <= expected_range[1]

    def test_ddmp_eligibility_rules(self, dr_service):
        """Test 9: DDMP eligibility follows 500kW threshold and 60-minute rules."""
        # Below threshold
        assert not dr_service._calculate_ddmp_eligible(400.0, 90, 50.0)  # Load too low
        assert not dr_service._calculate_ddmp_eligible(600.0, 30, 50.0)  # Duration too short
        assert not dr_service._calculate_ddmp_eligible(600.0, 90, 15.0)  # BESS too low

        # Meets all criteria
        assert dr_service._calculate_ddmp_eligible(600.0, 90, 50.0)
        assert dr_service._calculate_ddmp_eligible(500.0, 60, 20.0)  # At thresholds

        # No BESS
        assert dr_service._calculate_ddmp_eligible(600.0, 90, None)  # No BESS constraint

    @pytest.mark.asyncio
    async def test_min_priority_filtering(self, dr_service, mock_site, mock_zones):
        """Test 10: min_priority parameter correctly filters zones at repository level."""

        def get_zones_filtered(site_id, min_priority):
            """Mock that properly filters zones by min_priority."""
            return [z for z in mock_zones if z["priority"] >= min_priority]

        with (
            patch.object(dr_service, "_get_site", return_value=mock_site),
            patch.object(dr_service, "_get_thermal_runway", return_value=60),
            patch.object(dr_service, "_get_power_summary", return_value={"hvac_kw": 200.0}),
            patch.object(dr_service, "_get_zones", side_effect=lambda sid, mp: get_zones_filtered(sid, mp)),
            patch.object(dr_service, "_get_zone_hvac_load", return_value=40.0),
            patch.object(dr_service, "_get_bess_soc", return_value=50.0),
            patch.object(dr_service, "_get_data_freshness_seconds", return_value=30),
        ):
            # Test min_priority=1 (all zones)
            response_p1 = await dr_service.get_curtailable_load("site-002", min_priority=1)
            assert len(response_p1.zone_breakdown) == 5  # All zones

            # Test min_priority=3 (P3, P4, P5 only)
            response_p3 = await dr_service.get_curtailable_load("site-002", min_priority=3)
            assert len(response_p3.zone_breakdown) == 3  # P3, P4, P5
            assert all(z.priority >= 3 for z in response_p3.zone_breakdown)

            # Test min_priority=5 (P5 only)
            response_p5 = await dr_service.get_curtailable_load("site-002", min_priority=5)
            assert len(response_p5.zone_breakdown) == 1  # P5 only
            assert response_p5.zone_breakdown[0].priority == 5


class TestZoneCurtailableLoadCalculation:
    """Tests for zone-level curtailment calculations."""

    def test_full_headroom_full_curtailment(self, dr_service):
        """Zone with >= 2°C headroom can sustain 85% curtailment."""
        result = dr_service._calculate_zone_curtailable_kw(
            zone_current_load_kw=100.0,
            zone_temp_c=20.0,
            zone_setpoint_c=22.0,
            thermal_runway_minutes=60,
            zone_priority=3,
        )
        assert result == 85.0  # 100 * 0.85

    def test_partial_headroom_partial_curtailment(self, dr_service):
        """Zone with 1-2°C headroom gets partial curtailment."""
        result = dr_service._calculate_zone_curtailable_kw(
            zone_current_load_kw=100.0,
            zone_temp_c=21.0,
            zone_setpoint_c=22.0,
            thermal_runway_minutes=60,
            zone_priority=3,
        )
        # headroom=1.0, so (1.0/2.0) * 0.85 * 100 = 42.5
        assert result == 42.5

    def test_no_headroom_zero_curtailment(self, dr_service):
        """Zone at comfort boundary has zero curtailment."""
        result = dr_service._calculate_zone_curtailable_kw(
            zone_current_load_kw=100.0,
            zone_temp_c=22.5,
            zone_setpoint_c=22.0,
            thermal_runway_minutes=60,
            zone_priority=3,
        )
        assert result == 0.0

    def test_p1_priority_never_curtailed(self, dr_service):
        """P1 zones never curtailed regardless of headroom."""
        result = dr_service._calculate_zone_curtailable_kw(
            zone_current_load_kw=100.0,
            zone_temp_c=20.0,
            zone_setpoint_c=22.0,
            thermal_runway_minutes=60,
            zone_priority=1,
        )
        assert result == 0.0

    def test_p2_priority_half_curtailment(self, dr_service):
        """P2 zones get 50% curtailment multiplier."""
        result = dr_service._calculate_zone_curtailable_kw(
            zone_current_load_kw=100.0,
            zone_temp_c=20.0,
            zone_setpoint_c=22.0,
            thermal_runway_minutes=60,
            zone_priority=2,
        )
        assert result == 42.5  # 100 * 0.85 * 0.5


class TestLimitingFactorIdentification:
    """Tests for limiting factor logic."""

    def test_thermal_runway_short_limit(self, dr_service):
        """Short thermal runway (< 30 min) limits curtailment."""
        result = dr_service._identify_limiting_factor(
            thermal_runway_minutes=25,
            min_headroom_c=2.0,
            bess_soc_pct=50.0,
            zones_at_boundary=0,
        )
        assert result == "chiller_thermal_mass"

    def test_comfort_boundary_limit(self, dr_service):
        """Comfort boundary (< 1°C headroom) is limiting factor."""
        result = dr_service._identify_limiting_factor(
            thermal_runway_minutes=60,
            min_headroom_c=0.5,
            bess_soc_pct=50.0,
            zones_at_boundary=0,
        )
        assert result == "comfort_boundary"

    def test_bess_low_soc_limit(self, dr_service):
        """Low BESS SOC (< 20%) is limiting factor."""
        result = dr_service._identify_limiting_factor(
            thermal_runway_minutes=60,
            min_headroom_c=2.0,
            bess_soc_pct=15.0,
            zones_at_boundary=0,
        )
        assert result == "bess_low_soc"

    def test_zone_temperature_limit(self, dr_service):
        """Zones at temperature boundary is limiting factor."""
        result = dr_service._identify_limiting_factor(
            thermal_runway_minutes=60,
            min_headroom_c=2.0,
            bess_soc_pct=50.0,
            zones_at_boundary=2,
        )
        assert result == "zone_temperature_limit"

    def test_no_limit(self, dr_service):
        """No limiting factors returns 'none'."""
        result = dr_service._identify_limiting_factor(
            thermal_runway_minutes=90,
            min_headroom_c=2.0,
            bess_soc_pct=50.0,
            zones_at_boundary=0,
        )
        assert result == "none"
