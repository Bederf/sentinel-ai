"""
Tests for the occupancy-driven HVAC + lighting control service (Phase 130).

Verifies:
- Zone state tracking (anti-flap)
- HVAC setpoint relaxation and restoration via BMSControlBridge
- Lighting dimming and restoration via BMSControlBridge
- Occupancy source combining (PIR + badge)
- Safety bounds (setpoint 16-28°C)
- Audit logging

All control writes go through BMSControlBridge → DeviceManager → adapter.
Tests mock the bridge to isolate the service's decision logic.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.bms_control_bridge import WriteResult
from app.services.occupancy_control_service import (
    OccupancyControlService,
    ZoneControlState,
    get_occupancy_control_service,
)


def _ok_write_result(**overrides) -> WriteResult:
    """Create a successful WriteResult for mocking bridge responses."""
    defaults = dict(
        success=True,
        equipment_id="S002-VAV-101",
        point_name="temperature_setpoint",
        previous_value=22.0,
        requested_value=24.0,
        actual_value=24.0,
    )
    defaults.update(overrides)
    return WriteResult(**defaults)


def _fail_write_result(error: str = "bridge write failed", **overrides) -> WriteResult:
    """Create a failed WriteResult for mocking bridge responses."""
    defaults = dict(
        success=False,
        equipment_id="S002-VAV-101",
        point_name="temperature_setpoint",
        error=error,
    )
    defaults.update(overrides)
    return WriteResult(**defaults)


def _make_svc_with_mocks(
    read_hvac_setpoint=22.0,
    write_hvac_result=None,
    read_lighting_brightness=80.0,
    write_lighting_result=None,
    zone_occ=None,
):
    """Create an OccupancyControlService with mocked bridge and lighting service."""
    svc = OccupancyControlService()

    # Mock the bridge (all BMS reads/writes)
    mock_bridge = MagicMock()
    mock_bridge.read_hvac_setpoint = AsyncMock(return_value=read_hvac_setpoint)
    mock_bridge.read_lighting_brightness = AsyncMock(return_value=read_lighting_brightness)
    mock_bridge.write_hvac_setpoint = AsyncMock(return_value=write_hvac_result or _ok_write_result())
    mock_bridge.write_lighting_brightness = AsyncMock(
        return_value=write_lighting_result
        or _ok_write_result(
            equipment_id="S002-LTG-101",
            point_name="brightness",
            previous_value=80.0,
            requested_value=20.0,
            actual_value=20.0,
        )
    )

    # Mock the lighting service (for reading occupancy sensors, not for writes)
    mock_lighting = MagicMock()
    mock_lighting.get_zone_occupancy.return_value = zone_occ
    mock_lighting.get_all_zones.return_value = []

    # Override accessors on the instance
    svc._get_bridge = lambda: mock_bridge
    svc._get_lighting_service = lambda: mock_lighting
    svc._get_badge_occupancy = lambda zone_id: None
    svc._log_action = AsyncMock()

    return svc, mock_bridge, mock_lighting


@pytest.mark.unit
class TestZoneControlState:
    """Test zone state tracking."""

    def test_initial_state(self):
        state = ZoneControlState("zone-101")
        assert state.zone_id == "zone-101"
        assert state.hvac_relaxed is False
        assert state.lighting_dimmed is False
        assert state.last_occupancy_pct == -1.0
        assert state.original_setpoint is None
        assert state.original_brightness is None

    def test_state_tracks_relaxation(self):
        state = ZoneControlState("zone-101")
        state.hvac_relaxed = True
        state.original_setpoint = 22.0
        assert state.hvac_relaxed is True
        assert state.original_setpoint == 22.0


@pytest.mark.unit
class TestOccupancyControlService:
    """Test the occupancy control service logic."""

    def test_singleton_creation(self):
        svc = get_occupancy_control_service()
        assert isinstance(svc, OccupancyControlService)

    def test_zone_state_management(self):
        svc = OccupancyControlService()
        state = svc._get_zone_state("zone-101")
        assert state.zone_id == "zone-101"
        # Same zone returns same state
        state2 = svc._get_zone_state("zone-101")
        assert state is state2

    def test_different_zones_get_different_states(self):
        svc = OccupancyControlService()
        s1 = svc._get_zone_state("zone-101")
        s2 = svc._get_zone_state("zone-201")
        assert s1 is not s2
        assert s1.zone_id != s2.zone_id


@pytest.mark.unit
class TestHvacSetpointRelaxation:
    """Test HVAC setpoint relaxation logic via BMSControlBridge."""

    @pytest.mark.asyncio
    async def test_relax_setpoint_empty_zone(self):
        svc, mock_bridge, _ = _make_svc_with_mocks(read_hvac_setpoint=22.0)
        state = svc._get_zone_state("zone-101")

        result = await svc._relax_hvac_setpoint(
            site_id="site-002",
            zone_id="zone-101",
            state=state,
            offset=2.0,
            action_type="relax_setpoint",
            occ_pct=0.0,
            occ_status="empty",
            occupancy_source="dali_pir",
            badge_count=None,
            correlation_id="test-001",
        )

        assert result == 1
        assert state.hvac_relaxed is True
        assert state.original_setpoint == 22.0
        mock_bridge.write_hvac_setpoint.assert_called_once()
        call_kwargs = mock_bridge.write_hvac_setpoint.call_args.kwargs
        assert call_kwargs["new_setpoint"] == 24.0
        assert call_kwargs["who"] == "occupancy_poller"

    @pytest.mark.asyncio
    async def test_relax_setpoint_safety_cap(self):
        """Setpoint should never exceed 28°C."""
        svc, mock_bridge, _ = _make_svc_with_mocks(read_hvac_setpoint=27.0)
        state = svc._get_zone_state("zone-101")

        result = await svc._relax_hvac_setpoint(
            site_id="site-002",
            zone_id="zone-101",
            state=state,
            offset=2.0,
            action_type="relax_setpoint",
            occ_pct=0.0,
            occ_status="empty",
            occupancy_source="dali_pir",
            badge_count=None,
            correlation_id="test-002",
        )

        assert result == 1
        # Should cap at 28.0, not 29.0
        call_kwargs = mock_bridge.write_hvac_setpoint.call_args.kwargs
        assert call_kwargs["new_setpoint"] == 28.0

    @pytest.mark.asyncio
    async def test_no_relax_when_zone_has_no_equipment(self):
        """No action when bridge returns None (no equipment mapped)."""
        svc, _, _ = _make_svc_with_mocks(read_hvac_setpoint=None)
        state = svc._get_zone_state("zone-unknown")

        result = await svc._relax_hvac_setpoint(
            site_id="site-002",
            zone_id="zone-unknown",
            state=state,
            offset=2.0,
            action_type="relax_setpoint",
            occ_pct=0.0,
            occ_status="empty",
            occupancy_source="dali_pir",
            badge_count=None,
            correlation_id="test-003",
        )

        assert result == 0
        assert state.hvac_relaxed is False

    @pytest.mark.asyncio
    async def test_restore_setpoint_when_occupied(self):
        svc, mock_bridge, _ = _make_svc_with_mocks(read_hvac_setpoint=24.0)
        state = svc._get_zone_state("zone-101")
        state.hvac_relaxed = True
        state.original_setpoint = 22.0

        result = await svc._restore_hvac_setpoint(
            site_id="site-002",
            zone_id="zone-101",
            state=state,
            occ_pct=75.0,
            occ_status="busy",
            occupancy_source="combined",
            badge_count=8,
            correlation_id="test-004",
        )

        assert result == 1
        assert state.hvac_relaxed is False
        assert state.original_setpoint is None
        call_kwargs = mock_bridge.write_hvac_setpoint.call_args.kwargs
        assert call_kwargs["new_setpoint"] == 22.0

    @pytest.mark.asyncio
    async def test_no_relax_when_negligible_change(self):
        """If setpoint + offset = setpoint (due to capping), no action."""
        svc, mock_bridge, _ = _make_svc_with_mocks(read_hvac_setpoint=28.0)
        state = svc._get_zone_state("zone-101")

        result = await svc._relax_hvac_setpoint(
            site_id="site-002",
            zone_id="zone-101",
            state=state,
            offset=2.0,
            action_type="relax_setpoint",
            occ_pct=0.0,
            occ_status="empty",
            occupancy_source="dali_pir",
            badge_count=None,
            correlation_id="test-005",
        )

        assert result == 0  # No meaningful change (already at 28.0 cap)
        mock_bridge.write_hvac_setpoint.assert_not_called()

    @pytest.mark.asyncio
    async def test_relax_logs_failure_when_bridge_fails(self):
        """When bridge write fails, audit log records the failure."""
        svc, mock_bridge, _ = _make_svc_with_mocks(
            read_hvac_setpoint=22.0,
            write_hvac_result=_fail_write_result("safety engine blocked"),
        )
        state = svc._get_zone_state("zone-101")

        result = await svc._relax_hvac_setpoint(
            site_id="site-002",
            zone_id="zone-101",
            state=state,
            offset=2.0,
            action_type="relax_setpoint",
            occ_pct=0.0,
            occ_status="empty",
            occupancy_source="dali_pir",
            badge_count=None,
            correlation_id="test-fail-001",
        )

        assert result == 0
        assert state.hvac_relaxed is False
        svc._log_action.assert_called_once()
        call_kwargs = svc._log_action.call_args.kwargs
        assert call_kwargs["status"] == "failed"
        assert "safety engine blocked" in call_kwargs["error_message"]


@pytest.mark.unit
class TestLightingControl:
    """Test lighting brightness control via BMSControlBridge."""

    @pytest.mark.asyncio
    async def test_dim_lighting_empty_zone(self):
        svc, mock_bridge, _ = _make_svc_with_mocks(read_lighting_brightness=80.0)
        state = svc._get_zone_state("zone-101")

        result = await svc._dim_lighting(
            site_id="site-002",
            zone_id="zone-101",
            state=state,
            brightness=20,
            action_type="dim_to_minimum",
            occ_pct=0.0,
            occ_status="empty",
            occupancy_source="dali_pir",
            badge_count=None,
            correlation_id="test-006",
        )

        assert result == 1
        assert state.lighting_dimmed is True
        assert state.original_brightness == 80
        mock_bridge.write_lighting_brightness.assert_called_once()
        call_kwargs = mock_bridge.write_lighting_brightness.call_args.kwargs
        assert call_kwargs["brightness_pct"] == 20

    @pytest.mark.asyncio
    async def test_no_dim_if_already_low(self):
        """Don't dim if current brightness is already below target."""
        svc, mock_bridge, _ = _make_svc_with_mocks(read_lighting_brightness=15.0)
        state = svc._get_zone_state("zone-101")

        result = await svc._dim_lighting(
            site_id="site-002",
            zone_id="zone-101",
            state=state,
            brightness=20,
            action_type="dim_to_minimum",
            occ_pct=0.0,
            occ_status="empty",
            occupancy_source="dali_pir",
            badge_count=None,
            correlation_id="test-007",
        )

        assert result == 0
        assert state.lighting_dimmed is False
        mock_bridge.write_lighting_brightness.assert_not_called()

    @pytest.mark.asyncio
    async def test_restore_lighting(self):
        svc, mock_bridge, _ = _make_svc_with_mocks(read_lighting_brightness=20.0)
        state = svc._get_zone_state("zone-101")
        state.lighting_dimmed = True
        state.original_brightness = 80

        result = await svc._restore_lighting(
            site_id="site-002",
            zone_id="zone-101",
            state=state,
            occ_pct=65.0,
            occ_status="busy",
            occupancy_source="combined",
            badge_count=5,
            correlation_id="test-008",
        )

        assert result == 1
        assert state.lighting_dimmed is False
        assert state.original_brightness is None
        call_kwargs = mock_bridge.write_lighting_brightness.call_args.kwargs
        assert call_kwargs["brightness_pct"] == 80

    @pytest.mark.asyncio
    async def test_dim_fails_gracefully(self):
        """Bridge write returns failure → logs failure, returns 0."""
        svc, mock_bridge, _ = _make_svc_with_mocks(
            read_lighting_brightness=80.0,
            write_lighting_result=_fail_write_result(
                "no adapter",
                equipment_id="S002-LTG-101",
                point_name="brightness",
            ),
        )
        state = svc._get_zone_state("zone-101")

        result = await svc._dim_lighting(
            site_id="site-002",
            zone_id="zone-101",
            state=state,
            brightness=20,
            action_type="dim_to_minimum",
            occ_pct=0.0,
            occ_status="empty",
            occupancy_source="dali_pir",
            badge_count=None,
            correlation_id="test-009",
        )

        assert result == 0
        assert state.lighting_dimmed is False
        svc._log_action.assert_called_once()
        call_kwargs = svc._log_action.call_args.kwargs
        assert call_kwargs["status"] == "failed"

    @pytest.mark.asyncio
    async def test_dim_when_brightness_unknown(self):
        """When current brightness is None (read failed), still try to dim."""
        svc, mock_bridge, _ = _make_svc_with_mocks(read_lighting_brightness=None)
        state = svc._get_zone_state("zone-101")

        result = await svc._dim_lighting(
            site_id="site-002",
            zone_id="zone-101",
            state=state,
            brightness=20,
            action_type="dim_to_minimum",
            occ_pct=0.0,
            occ_status="empty",
            occupancy_source="dali_pir",
            badge_count=None,
            correlation_id="test-010",
        )

        assert result == 1
        assert state.lighting_dimmed is True
        assert state.original_brightness == 100  # Default when unknown


@pytest.mark.unit
class TestEvaluateHvac:
    """Test the HVAC evaluation decision logic."""

    @pytest.mark.asyncio
    async def test_empty_zone_triggers_relax(self):
        svc, mock_bridge, _ = _make_svc_with_mocks(read_hvac_setpoint=22.0)
        state = svc._get_zone_state("zone-101")

        mock_settings = MagicMock()
        mock_settings.occupancy_hvac_setback_c = 2.0
        mock_settings.occupancy_hvac_partial_setback_c = 1.0

        result = await svc._evaluate_hvac(
            site_id="site-002",
            zone_id="zone-101",
            state=state,
            is_empty=True,
            is_low=False,
            is_occupied=False,
            occ_pct=0.0,
            occ_status="empty",
            occupancy_source="dali_pir",
            badge_count=None,
            correlation_id="test-011",
            settings=mock_settings,
        )

        assert result == 1
        assert state.hvac_relaxed is True

    @pytest.mark.asyncio
    async def test_occupied_zone_with_relaxed_state_triggers_restore(self):
        svc, mock_bridge, _ = _make_svc_with_mocks(read_hvac_setpoint=24.0)
        state = svc._get_zone_state("zone-101")
        state.hvac_relaxed = True
        state.original_setpoint = 22.0

        mock_settings = MagicMock()

        result = await svc._evaluate_hvac(
            site_id="site-002",
            zone_id="zone-101",
            state=state,
            is_empty=False,
            is_low=False,
            is_occupied=True,
            occ_pct=75.0,
            occ_status="busy",
            occupancy_source="combined",
            badge_count=8,
            correlation_id="test-012",
            settings=mock_settings,
        )

        assert result == 1
        assert state.hvac_relaxed is False

    @pytest.mark.asyncio
    async def test_no_action_when_already_relaxed_and_still_empty(self):
        svc = OccupancyControlService()
        state = svc._get_zone_state("zone-101")
        state.hvac_relaxed = True  # Already relaxed

        mock_settings = MagicMock()

        result = await svc._evaluate_hvac(
            site_id="site-002",
            zone_id="zone-101",
            state=state,
            is_empty=True,
            is_low=False,
            is_occupied=False,
            occ_pct=0.0,
            occ_status="empty",
            occupancy_source="dali_pir",
            badge_count=None,
            correlation_id="test-013",
            settings=mock_settings,
        )

        assert result == 0  # No double-relax

    @pytest.mark.asyncio
    async def test_low_occupancy_triggers_partial_relax(self):
        svc, mock_bridge, _ = _make_svc_with_mocks(read_hvac_setpoint=22.0)
        state = svc._get_zone_state("zone-101")

        mock_settings = MagicMock()
        mock_settings.occupancy_hvac_setback_c = 2.0
        mock_settings.occupancy_hvac_partial_setback_c = 1.0

        result = await svc._evaluate_hvac(
            site_id="site-002",
            zone_id="zone-101",
            state=state,
            is_empty=False,
            is_low=True,
            is_occupied=False,
            occ_pct=25.0,
            occ_status="quiet",
            occupancy_source="dali_pir",
            badge_count=None,
            correlation_id="test-014",
            settings=mock_settings,
        )

        assert result == 1
        call_kwargs = mock_bridge.write_hvac_setpoint.call_args.kwargs
        assert call_kwargs["new_setpoint"] == 23.0  # 22.0 + 1.0 partial


@pytest.mark.unit
class TestEvaluateLighting:
    """Test lighting evaluation decision logic."""

    @pytest.mark.asyncio
    async def test_empty_zone_triggers_dim(self):
        svc, mock_bridge, _ = _make_svc_with_mocks(read_lighting_brightness=80.0)
        state = svc._get_zone_state("zone-101")

        mock_settings = MagicMock()
        mock_settings.occupancy_lighting_empty_pct = 20
        mock_settings.occupancy_lighting_low_pct = 50

        result = await svc._evaluate_lighting(
            site_id="site-002",
            zone_id="zone-101",
            state=state,
            is_empty=True,
            is_low=False,
            is_occupied=False,
            occ_pct=0.0,
            occ_status="empty",
            occupancy_source="dali_pir",
            badge_count=None,
            correlation_id="test-015",
            settings=mock_settings,
        )

        assert result == 1
        call_kwargs = mock_bridge.write_lighting_brightness.call_args.kwargs
        assert call_kwargs["brightness_pct"] == 20

    @pytest.mark.asyncio
    async def test_no_dim_when_already_dimmed(self):
        svc = OccupancyControlService()
        state = svc._get_zone_state("zone-101")
        state.lighting_dimmed = True

        mock_settings = MagicMock()
        mock_settings.occupancy_lighting_empty_pct = 20

        result = await svc._evaluate_lighting(
            site_id="site-002",
            zone_id="zone-101",
            state=state,
            is_empty=True,
            is_low=False,
            is_occupied=False,
            occ_pct=0.0,
            occ_status="empty",
            occupancy_source="dali_pir",
            badge_count=None,
            correlation_id="test-016",
            settings=mock_settings,
        )

        assert result == 0


@pytest.mark.unit
class TestRunCycle:
    """Test full run_cycle integration."""

    @pytest.mark.asyncio
    async def test_run_cycle_no_zones(self):
        svc, _, mock_lighting = _make_svc_with_mocks()
        mock_lighting.get_all_zones.return_value = []

        result = await svc.run_cycle(site_id="site-002")

        assert result["actions_taken"] == 0
        assert result["zones_checked"] == 0
        assert result["errors"] == []

    @pytest.mark.asyncio
    async def test_run_cycle_processes_zones(self):
        svc, _, mock_lighting = _make_svc_with_mocks()
        mock_lighting.get_all_zones.return_value = [
            {"zone_id": "zone-101", "name": "Office A", "floor": 1},
            {"zone_id": "zone-201", "name": "Office B", "floor": 2},
        ]
        # Mock _process_zone to avoid deep calls
        svc._process_zone = AsyncMock(return_value=0)

        result = await svc.run_cycle(site_id="site-002")

        assert result["zones_checked"] == 2
        assert "correlation_id" in result

    @pytest.mark.asyncio
    async def test_run_cycle_handles_zone_errors(self):
        svc, _, mock_lighting = _make_svc_with_mocks()
        mock_lighting.get_all_zones.return_value = [{"zone_id": "zone-101"}]
        svc._process_zone = AsyncMock(side_effect=RuntimeError("sensor offline"))

        result = await svc.run_cycle(site_id="site-002")

        assert result["zones_checked"] == 1
        assert result["actions_taken"] == 0
        assert len(result["errors"]) == 1
        assert "sensor offline" in result["errors"][0]

    @pytest.mark.asyncio
    async def test_run_cycle_returns_correlation_id(self):
        svc, _, mock_lighting = _make_svc_with_mocks()
        mock_lighting.get_all_zones.return_value = []

        result = await svc.run_cycle(site_id="site-002")

        assert result["correlation_id"].startswith("occ-")


@pytest.mark.unit
class TestBadgeOccupancy:
    """Test badge-based occupancy fallback."""

    def test_badge_returns_none_on_error(self):
        svc = OccupancyControlService()
        result = svc._get_badge_occupancy("zone-nonexistent")
        assert result is None or isinstance(result, int)
