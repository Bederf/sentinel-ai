"""Tests for ContextPreComputeService (Phase 1b)."""

from datetime import UTC, datetime, timedelta

import pytest

from app.services.context_precompute_service import (
    ContextPreComputeService,
    PreComputedContext,
)
from app.services.fcu_state_tracker import (
    FCUStateTracker,
    InMemoryBackend,
    WasteOpportunity,
)

UTC = UTC
NOW = datetime(2026, 4, 27, 12, 0, 0, tzinfo=UTC)


def make_tracker(profile: str = "balanced") -> FCUStateTracker:
    """Create a fresh FCUStateTracker with InMemoryBackend."""
    return FCUStateTracker(active_profile=profile, backend=InMemoryBackend())


def poll(tracker, zone_id, occupancy_pct, room_temp_c, setpoint_c=None, delta_minutes=0):
    """Helper: record a poll at a given offset from NOW."""
    ts = NOW + timedelta(minutes=delta_minutes)
    tracker.record_poll(zone_id, occupancy_pct, room_temp_c, setpoint_c, ts)


class TestFCUPostOccupancyIntegration:
    """Rule 1: FCU post-occupancy waste from FCUStateTracker."""

    @pytest.mark.asyncio
    async def test_empty_building_fcus_waste(self):
        """Empty building with cooling FCUs → waste candidates from FCU tracker."""
        tracker = make_tracker("cost_saving")  # 5 min threshold
        # Zone empties and FCU keeps cooling
        poll(tracker, "Zone-201", 80.0, 22.5, 24.0, delta_minutes=0)
        poll(tracker, "Zone-201", 0.0, 22.0, 24.0, delta_minutes=5)
        # After 6 min empty — past cost_saving threshold
        poll(tracker, "Zone-201", 0.0, 21.5, 24.0, delta_minutes=12)

        service = ContextPreComputeService(tracker)
        conditions = {
            "ahu_states": [],
            "building_occupancy_pct": 0,
            "bess_soc": 50,
            "bess_dispatching": False,
            "indoor_avg_temp": 22.0,
        }

        ctx = await service.compute(
            site_id="site-002",
            current_conditions=conditions,
            active_profile="cost_saving",
            outdoor_temp=18.0,
            peak_tariff=3.01,
        )

        assert any(o.opportunity_type == "fcu_post_occupancy" for o in ctx.opportunities)

    @pytest.mark.asyncio
    async def test_occupied_zone_no_fcu_waste(self):
        """Zone occupied → no FCU waste regardless of temperature."""
        tracker = make_tracker()
        poll(tracker, "Zone-201", 80.0, 22.5, 24.0, delta_minutes=0)

        service = ContextPreComputeService(tracker)
        conditions = {
            "ahu_states": [],
            "building_occupancy_pct": 80,
            "bess_soc": 50,
            "bess_dispatching": True,
            "indoor_avg_temp": 22.0,
        }

        ctx = await service.compute(
            site_id="site-002",
            current_conditions=conditions,
            active_profile="balanced",
            outdoor_temp=18.0,
            peak_tariff=3.01,
        )

        assert not any(o.opportunity_type == "fcu_post_occupancy" for o in ctx.opportunities)


class TestAHUOvercapacity:
    """Rule 2: AHU overcapacity detection."""

    @pytest.mark.asyncio
    async def test_ahu_overcapacity_flagged(self):
        """Building 8% occupied, AHU at 80% → overcapacity waste."""
        tracker = make_tracker()
        service = ContextPreComputeService(tracker)

        conditions = {
            "ahu_states": [{"equipment_id": "S002-AHU-B1-001", "capacity_pct": 80}],
            "building_occupancy_pct": 8,
            "bess_soc": 50,
            "bess_dispatching": False,
            "indoor_avg_temp": 22.0,
        }

        ctx = await service.compute(
            site_id="site-002",
            current_conditions=conditions,
            active_profile="cost_saving",
            outdoor_temp=18.0,
            peak_tariff=3.01,
        )

        overcapacity = [o for o in ctx.opportunities if o.opportunity_type == "overcapacity"]
        assert len(overcapacity) == 1
        assert overcapacity[0].equipment_id == "S002-AHU-B1-001"
        assert overcapacity[0].estimated_saving_kwh is not None

    @pytest.mark.asyncio
    async def test_ahu_below_threshold_not_flagged(self):
        """AHU at 60% when building 15% occupied → not flagged."""
        tracker = make_tracker()
        service = ContextPreComputeService(tracker)

        conditions = {
            "ahu_states": [{"equipment_id": "S002-AHU-B1-001", "capacity_pct": 60}],
            "building_occupancy_pct": 15,
            "bess_soc": 50,
            "bess_dispatching": False,
            "indoor_avg_temp": 22.0,
        }

        ctx = await service.compute(
            site_id="site-002",
            current_conditions=conditions,
            active_profile="cost_saving",
            outdoor_temp=18.0,
            peak_tariff=3.01,
        )

        assert not any(o.opportunity_type == "overcapacity" for o in ctx.opportunities)

    @pytest.mark.asyncio
    async def test_high_occupancy_not_flagged(self):
        """Building 50% occupied → no overcapacity even with AHU at 80%."""
        tracker = make_tracker()
        service = ContextPreComputeService(tracker)

        conditions = {
            "ahu_states": [{"equipment_id": "S002-AHU-B1-001", "capacity_pct": 80}],
            "building_occupancy_pct": 50,
            "bess_soc": 50,
            "bess_dispatching": False,
            "indoor_avg_temp": 22.0,
        }

        ctx = await service.compute(
            site_id="site-002",
            current_conditions=conditions,
            active_profile="balanced",
            outdoor_temp=18.0,
            peak_tariff=3.01,
        )

        assert not any(o.opportunity_type == "overcapacity" for o in ctx.opportunities)


class TestFreeCooling:
    """Rule 3: Free cooling opportunity detection."""

    @pytest.mark.asyncio
    async def test_free_cooling_opportunity(self):
        """Outdoor 15°C, indoor 22°C (7°C differential) → free cooling flagged."""
        tracker = make_tracker()
        service = ContextPreComputeService(tracker)

        conditions = {
            "ahu_states": [],
            "building_occupancy_pct": 50,
            "bess_soc": 50,
            "bess_dispatching": False,
            "indoor_avg_temp": 22.0,
        }

        ctx = await service.compute(
            site_id="site-002",
            current_conditions=conditions,
            active_profile="cost_saving",
            outdoor_temp=15.0,  # 7°C differential
            peak_tariff=3.01,
        )

        free_cooling = [o for o in ctx.opportunities if o.opportunity_type == "free_cooling"]
        assert len(free_cooling) == 1
        assert free_cooling[0].confidence == 0.85

    @pytest.mark.asyncio
    async def test_no_free_cooling_insufficient_delta(self):
        """Outdoor 20°C, indoor 21°C (1°C differential) → no free cooling."""
        tracker = make_tracker()
        service = ContextPreComputeService(tracker)

        conditions = {
            "ahu_states": [],
            "building_occupancy_pct": 50,
            "bess_soc": 50,
            "bess_dispatching": False,
            "indoor_avg_temp": 21.0,
        }

        ctx = await service.compute(
            site_id="site-002",
            current_conditions=conditions,
            active_profile="cost_saving",
            outdoor_temp=20.0,
            peak_tariff=3.01,
        )

        assert not any(o.opportunity_type == "free_cooling" for o in ctx.opportunities)

    @pytest.mark.asyncio
    async def test_no_free_cooling_missing_indoor_temp(self):
        """No indoor_avg_temp → free cooling skipped."""
        tracker = make_tracker()
        service = ContextPreComputeService(tracker)

        conditions = {
            "ahu_states": [],
            "building_occupancy_pct": 50,
            "bess_soc": 50,
            "bess_dispatching": False,
            "indoor_avg_temp": None,
        }

        ctx = await service.compute(
            site_id="site-002",
            current_conditions=conditions,
            active_profile="cost_saving",
            outdoor_temp=15.0,
            peak_tariff=3.01,
        )

        assert not any(o.opportunity_type == "free_cooling" for o in ctx.opportunities)

    @pytest.mark.asyncio
    async def test_no_free_cooling_outdoor_too_warm(self):
        """Outdoor 23°C, indoor 22°C → not cool enough for free cooling."""
        tracker = make_tracker()
        service = ContextPreComputeService(tracker)

        conditions = {
            "ahu_states": [],
            "building_occupancy_pct": 50,
            "bess_soc": 50,
            "bess_dispatching": False,
            "indoor_avg_temp": 22.0,
        }

        ctx = await service.compute(
            site_id="site-002",
            current_conditions=conditions,
            active_profile="balanced",
            outdoor_temp=23.0,
            peak_tariff=3.01,
        )

        assert not any(o.opportunity_type == "free_cooling" for o in ctx.opportunities)


class TestBESSDispatch:
    """Rule 4: BESS idle during peak tariff detection."""

    @pytest.mark.asyncio
    async def test_bess_idle_during_peak(self):
        """BESS idle (not dispatching) during peak tariff → dispatch opportunity."""
        tracker = make_tracker()
        service = ContextPreComputeService(tracker)

        conditions = {
            "ahu_states": [],
            "building_occupancy_pct": 50,
            "bess_soc": 50,
            "bess_dispatching": False,  # idle
            "indoor_avg_temp": 22.0,
        }

        ctx = await service.compute(
            site_id="site-002",
            current_conditions=conditions,
            active_profile="cost_saving",
            outdoor_temp=18.0,
            peak_tariff=3.01,
        )

        bess = [o for o in ctx.opportunities if o.opportunity_type == "bess_idle_peak"]
        assert len(bess) == 1
        assert bess[0].confidence == 0.95
        assert "idle" in bess[0].description.lower()

    @pytest.mark.asyncio
    async def test_bess_not_flagged_when_dispatching(self):
        """BESS actively dispatching → not flagged as idle."""
        tracker = make_tracker()
        service = ContextPreComputeService(tracker)

        conditions = {
            "ahu_states": [],
            "building_occupancy_pct": 50,
            "bess_soc": 50,
            "bess_dispatching": True,  # actively dispatching
            "indoor_avg_temp": 22.0,
        }

        ctx = await service.compute(
            site_id="site-002",
            current_conditions=conditions,
            active_profile="cost_saving",
            outdoor_temp=18.0,
            peak_tariff=3.01,
        )

        assert not any(o.opportunity_type == "bess_idle_peak" for o in ctx.opportunities)

    @pytest.mark.asyncio
    async def test_bess_not_flagged_low_soc(self):
        """BESS SOC below 20% → not flagged (not enough energy to dispatch)."""
        tracker = make_tracker()
        service = ContextPreComputeService(tracker)

        conditions = {
            "ahu_states": [],
            "building_occupancy_pct": 50,
            "bess_soc": 15,  # below 20%
            "bess_dispatching": False,
            "indoor_avg_temp": 22.0,
        }

        ctx = await service.compute(
            site_id="site-002",
            current_conditions=conditions,
            active_profile="cost_saving",
            outdoor_temp=18.0,
            peak_tariff=3.01,
        )

        assert not any(o.opportunity_type == "bess_idle_peak" for o in ctx.opportunities)


class TestMultipleOpportunities:
    """Multiple rules can fire simultaneously."""

    @pytest.mark.asyncio
    async def test_fcu_and_bess_both_flagged(self):
        """FCU post-occupancy + BESS idle → both in opportunities list."""
        tracker = make_tracker("cost_saving")
        poll(tracker, "Zone-201", 80.0, 22.5, 24.0, delta_minutes=0)
        poll(tracker, "Zone-201", 0.0, 22.0, 24.0, delta_minutes=5)
        poll(tracker, "Zone-201", 0.0, 21.5, 24.0, delta_minutes=12)

        service = ContextPreComputeService(tracker)
        conditions = {
            "ahu_states": [],
            "building_occupancy_pct": 0,
            "bess_soc": 50,
            "bess_dispatching": False,
            "indoor_avg_temp": 22.0,
        }

        ctx = await service.compute(
            site_id="site-002",
            current_conditions=conditions,
            active_profile="cost_saving",
            outdoor_temp=18.0,
            peak_tariff=3.01,
        )

        opp_types = {o.opportunity_type for o in ctx.opportunities}
        assert "fcu_post_occupancy" in opp_types
        assert "bess_idle_peak" in opp_types


class TestPreComputedContext:
    """PreComputedContext dataclass fields."""

    @pytest.mark.asyncio
    async def test_computed_at_is_utcnow(self):
        tracker = make_tracker()
        service = ContextPreComputeService(tracker)

        conditions = {
            "ahu_states": [],
            "building_occupancy_pct": 100,
            "bess_soc": 50,
            "bess_dispatching": True,
            "indoor_avg_temp": 22.0,
        }

        before = datetime.utcnow()
        ctx = await service.compute(
            site_id="site-002",
            current_conditions=conditions,
            active_profile="balanced",
            outdoor_temp=18.0,
            peak_tariff=3.01,
        )
        after = datetime.utcnow()

        assert before <= ctx.computed_at <= after
        assert ctx.active_profile == "balanced"

    @pytest.mark.asyncio
    async def test_all_conditions_keys_optional(self):
        """compute() handles missing keys gracefully."""
        tracker = make_tracker()
        service = ContextPreComputeService(tracker)

        # Only site_id and active_profile are required; current_conditions can be empty
        ctx = await service.compute(
            site_id="site-002",
            current_conditions={},
            active_profile="balanced",
            outdoor_temp=None,
            peak_tariff=3.01,
        )

        assert ctx.computed_at is not None
        assert ctx.active_profile == "balanced"


class TestFormatForPrompt:
    """format_for_prompt() output format."""

    def test_empty_returns_empty_string(self):
        tracker = make_tracker()
        service = ContextPreComputeService(tracker)

        ctx = PreComputedContext(
            opportunities=[],
            computed_at=datetime.utcnow(),
            active_profile="cost_saving",
        )
        assert service.format_for_prompt(ctx) == ""

    def test_single_opportunity_formatted(self):
        tracker = make_tracker()
        service = ContextPreComputeService(tracker)

        opp = WasteOpportunity(
            equipment_id="S002-FCU-201",
            zone_id="Zone-201",
            opportunity_type="fcu_post_occupancy",
            minutes_elapsed=18.0,
            confidence=0.85,
            description="Zone-201 empty 18 min, FCU still running",
            estimated_saving_kwh=0.34,
        )
        ctx = PreComputedContext(
            opportunities=[opp],
            computed_at=datetime.utcnow(),
            active_profile="cost_saving",
        )

        output = service.format_for_prompt(ctx)
        assert "WASTE OPPORTUNITIES DETECTED" in output
        assert "S002-FCU-201" in output
        assert "18" in output
        assert "⚠️" in output

    def test_kwh_saving_shown_when_available(self):
        tracker = make_tracker()
        service = ContextPreComputeService(tracker)

        opp = WasteOpportunity(
            equipment_id="S002-AHU-B1-001",
            zone_id="",
            opportunity_type="overcapacity",
            minutes_elapsed=0,
            confidence=0.90,
            description="Building 8% occupied, AHU at 80% capacity",
            estimated_saving_kwh=2.4,
        )
        ctx = PreComputedContext(
            opportunities=[opp],
            computed_at=datetime.utcnow(),
            active_profile="balanced",
        )

        output = service.format_for_prompt(ctx)
        assert "2.4" in output or "2" in output  # kWh value appears
        assert "kwh" in output.lower()

    def test_multiple_opportunities_all_listed(self):
        tracker = make_tracker()
        service = ContextPreComputeService(tracker)

        opportunities = [
            WasteOpportunity(
                equipment_id="S002-FCU-201",
                zone_id="Zone-201",
                opportunity_type="fcu_post_occupancy",
                minutes_elapsed=15.0,
                confidence=0.85,
                description="Zone-201 empty 15 min, FCU still running",
            ),
            WasteOpportunity(
                equipment_id="BESS-1",
                zone_id="site",
                opportunity_type="bess_idle_peak",
                minutes_elapsed=0,
                confidence=0.95,
                description="BESS idle during peak tariff",
            ),
        ]
        ctx = PreComputedContext(
            opportunities=opportunities,
            computed_at=datetime.utcnow(),
            active_profile="cost_saving",
        )

        output = service.format_for_prompt(ctx)
        assert output.count("⚠️") == 2
        assert "S002-FCU-201" in output
        assert "BESS-1" in output
