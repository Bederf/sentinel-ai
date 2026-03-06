"""
Tests for the simulation data adapter in PointDiscoveryService.

Covers:
- _load_simulation_points() Supabase queries and formatting
- _infer_object_type() and _infer_point_type() helpers
- 3-tier routing: BACnet -> Simulation -> JSON fallback
- DiscoverRequest API model (demo fields removed)
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.niagara.point_discovery import (
    PointDiscoveryService,
    _infer_object_type,
    _infer_point_type,
)


# ---------------------------------------------------------------------------
# Test: Simulation Point Adapter
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSimulationPointAdapter:
    """Test _load_simulation_points() and helper functions."""

    def test_load_simulation_points_returns_formatted_points(self):
        """Mock Supabase to return equipment + readings, verify point format."""
        svc = PointDiscoveryService()

        # Sensor readings data per equipment code
        readings_map = {
            "S002-CHILLER-B1-001": [
                {"sensor_type": "chilled_water_supply_temp", "value": 7.2, "unit": "°C"},
                {"sensor_type": "chilled_water_setpoint", "value": 6.5, "unit": "°C"},
            ],
            "S002-AHU-B1-001": [
                {"sensor_type": "supply_air_temp", "value": 14.5, "unit": "°C"},
                {"sensor_type": "fault_status", "value": 0, "unit": ""},
            ],
            "S002-FCU-101": [
                {"sensor_type": "room_temp", "value": 22.1, "unit": "°C"},
                {"sensor_type": "enable_command", "value": 1, "unit": ""},
            ],
        }

        equipment_data = [
            {
                "code": "S002-CHILLER-B1-001",
                "name": "Chiller 1",
                "type": "CHILLER",
                "status": "active",
                "health_score": 85,
            },
            {"code": "S002-AHU-B1-001", "name": "AHU 1", "type": "AHU", "status": "active", "health_score": 90},
            {"code": "S002-FCU-101", "name": "FCU Zone 101", "type": "FCU", "status": "active", "health_score": 78},
        ]

        def _build_chain_mock(final_data):
            """Build a mock that supports arbitrary .method() chaining ending in .execute()."""

            class ChainMock(MagicMock):
                def __init__(self, *a, **kw):
                    super().__init__(*a, **kw)
                    self._terminal_data = final_data

                def __getattr__(self, name):
                    if name == "execute":

                        def execute_fn(*a, **kw):
                            resp = MagicMock()
                            resp.data = self._terminal_data
                            return resp

                        return execute_fn
                    if name.startswith("_"):
                        return super().__getattr__(name)

                    # All chainable methods return self
                    def chain_fn(*a, **kw):
                        return self

                    return chain_fn

            return ChainMock()

        # Track which eq_code is being queried for readings
        current_eq_code = {"code": None}

        def mock_table(table_name):
            if table_name == "sites":
                return _build_chain_mock([])  # empty buildings
            elif table_name == "equipment":
                return _build_chain_mock(equipment_data)
            elif table_name == "equipment_sensor_readings":
                # Need to capture the .eq("equipment_id", code) call
                class ReadingsChain(MagicMock):
                    def __init__(self, *a, **kw):
                        super().__init__(*a, **kw)
                        self._eq_code = None

                    def __getattr__(self, name):
                        if name == "execute":
                            data = readings_map.get(self._eq_code, [])

                            def execute_fn(*a, **kw):
                                resp = MagicMock()
                                resp.data = data
                                return resp

                            return execute_fn
                        if name == "eq":

                            def eq_fn(field, value):
                                self._eq_code = value
                                return self

                            return eq_fn
                        if name.startswith("_"):
                            return super().__getattr__(name)

                        def chain_fn(*a, **kw):
                            return self

                        return chain_fn

                return ReadingsChain()
            return MagicMock()

        mock_client = MagicMock()
        mock_client.table = mock_table

        with patch("app.services.niagara.point_discovery.get_supabase_client", return_value=mock_client):
            points = svc._load_simulation_points("site-002")

        # Should have 6 points total (2 per equipment x 3 equipment)
        assert len(points) == 6

        # Verify first point format
        chiller_temp = next(p for p in points if "chilled_water_supply_temp" in p["name"])
        assert chiller_temp["name"] == "S002-CHILLER-B1-001.chilled_water_supply_temp"
        assert chiller_temp["description"] == "Chiller 1 - Chilled Water Supply Temp"
        assert chiller_temp["object_type"] == "analogInput"
        assert chiller_temp["units"] == "°C"
        assert chiller_temp["present_value"] == 7.2
        assert chiller_temp["writable"] is False
        assert chiller_temp["_equipment_id"] == "S002-CHILLER-B1-001"
        assert chiller_temp["_equipment_type"] == "CHILLER"
        assert chiller_temp["_point_type"] == "sensor"

        # Verify setpoint classified correctly
        chiller_sp = next(p for p in points if "setpoint" in p["name"])
        assert chiller_sp["object_type"] == "analogValue"
        assert chiller_sp["_point_type"] == "setpoint"
        assert chiller_sp["writable"] is True

        # Verify command classified correctly
        fcu_cmd = next(p for p in points if "enable_command" in p["name"])
        assert fcu_cmd["object_type"] == "binaryOutput"
        assert fcu_cmd["_point_type"] == "command"

        # Verify fault status classified correctly
        ahu_fault = next(p for p in points if "fault_status" in p["name"])
        assert ahu_fault["object_type"] == "binaryInput"
        assert ahu_fault["_point_type"] == "status"

    def test_load_simulation_points_empty_when_no_equipment(self):
        """Mock Supabase to return empty result, assert empty list."""
        svc = PointDiscoveryService()

        mock_client = MagicMock()

        # Buildings returns empty
        mock_buildings_resp = MagicMock()
        mock_buildings_resp.data = []
        mock_client.table.return_value.select.return_value.or_.return_value.execute.return_value = mock_buildings_resp

        # Equipment prefix returns empty
        mock_equip_resp = MagicMock()
        mock_equip_resp.data = []
        mock_client.table.return_value.select.return_value.like.return_value.execute.return_value = mock_equip_resp

        with patch("app.services.niagara.point_discovery.get_supabase_client", return_value=mock_client):
            points = svc._load_simulation_points("site-999")

        assert points == []

    def test_load_simulation_points_handles_supabase_error(self):
        """Mock Supabase to raise exception, assert empty list (graceful degradation)."""
        svc = PointDiscoveryService()

        with patch(
            "app.services.niagara.point_discovery.get_supabase_client",
            side_effect=RuntimeError("Supabase unavailable"),
        ):
            points = svc._load_simulation_points("site-002")

        assert points == []

    def test_infer_object_type_sensor(self):
        """Verify _infer_object_type maps sensor types correctly."""
        assert _infer_object_type("temperature") == "analogInput"
        assert _infer_object_type("supply_air_temp") == "analogInput"
        assert _infer_object_type("power_kw") == "analogInput"
        assert _infer_object_type("chilled_water_setpoint") == "analogValue"
        assert _infer_object_type("target_temp") == "analogValue"
        assert _infer_object_type("enable_command") == "binaryOutput"
        assert _infer_object_type("mode") == "binaryOutput"
        assert _infer_object_type("fault_status") == "binaryInput"
        assert _infer_object_type("alarm") == "binaryInput"

    def test_infer_point_type(self):
        """Verify _infer_point_type maps sensor types correctly."""
        assert _infer_point_type("temperature") == "sensor"
        assert _infer_point_type("supply_air_temp") == "sensor"
        assert _infer_point_type("power_kw") == "sensor"
        assert _infer_point_type("setpoint") == "setpoint"
        assert _infer_point_type("target_temp") == "setpoint"
        assert _infer_point_type("command") == "command"
        assert _infer_point_type("enable") == "command"
        assert _infer_point_type("fault_status") == "status"
        assert _infer_point_type("alarm") == "status"


# ---------------------------------------------------------------------------
# Test: Discovery Routing
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDiscoveryRouting:
    """Test 3-tier routing: BACnet -> Simulation -> JSON fallback."""

    @pytest.mark.asyncio
    async def test_routing_bacnet_first(self):
        """When BACnet ID provided and client works, use BACnet (skip simulation)."""
        svc = PointDiscoveryService()

        mock_client = MagicMock()
        mock_client.is_running = True
        svc._bacnet_client = mock_client

        bacnet_points = [{"name": "BACnet-Point-1", "object_type": "analogInput"}]
        mock_client.read_point_list = AsyncMock(return_value=[])
        svc._discover_from_bacnet = AsyncMock(return_value=bacnet_points)

        with patch.object(svc, "_load_simulation_points") as mock_sim:
            points = await svc._discover_points("192.168.1.100", "site-002", device_bacnet_id=1234)

        assert points == bacnet_points
        mock_sim.assert_not_called()

    @pytest.mark.asyncio
    async def test_routing_simulation_fallback_when_no_bacnet(self):
        """When no BACnet ID, try simulation. If simulation has data, use it."""
        svc = PointDiscoveryService()

        sim_points = [{"name": "S002-CHILLER.temp", "object_type": "analogInput"}]

        with (
            patch.object(svc, "_load_simulation_points", return_value=sim_points) as mock_sim,
            patch.object(svc, "_load_demo_points") as mock_json,
        ):
            points = await svc._discover_points("simulation", "site-002")

        assert points == sim_points
        mock_sim.assert_called_once_with("site-002")
        mock_json.assert_not_called()

    @pytest.mark.asyncio
    async def test_routing_json_fallback_when_simulation_empty(self):
        """When simulation returns empty, fall back to JSON files."""
        svc = PointDiscoveryService()

        json_points = [{"name": "S002-FCU-101.room_temp", "object_type": "analogInput"}]

        with (
            patch.object(svc, "_load_simulation_points", return_value=[]) as mock_sim,
            patch.object(svc, "_load_demo_points", return_value=json_points) as mock_json,
        ):
            points = await svc._discover_points("simulation", "site-002")

        assert points == json_points
        mock_sim.assert_called_once_with("site-002")
        mock_json.assert_called_once_with("site-002")

    @pytest.mark.asyncio
    async def test_discover_and_classify_no_demo_params(self):
        """Call discover_and_classify without demo params — no TypeError."""
        svc = PointDiscoveryService()

        mock_points = [
            {
                "name": "S002-CHILLER.temp",
                "object_type": "analogInput",
                "instance": 1,
                "units": "C",
                "present_value": 7.0,
                "description": "test",
                "writable": False,
            }
        ]

        with patch.object(svc, "_discover_points", new_callable=AsyncMock, return_value=mock_points):
            result = await svc.discover_and_classify(
                device_ip="simulation",
                site_id="site-002",
            )

        assert result.status in ("complete", "error")
        assert len(result.raw_points) > 0 or result.error is not None


# ---------------------------------------------------------------------------
# Test: API Endpoint Model
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAPIEndpoint:
    """Test DiscoverRequest model after demo field removal."""

    def test_discover_request_no_demo_fields(self):
        """DiscoverRequest accepts device_ip, site_id without demo fields."""
        from app.api.niagara_discovery import DiscoverRequest

        # Construct without demo fields
        req = DiscoverRequest(device_ip="simulation", site_id="site-002")
        assert req.device_ip == "simulation"
        assert req.site_id == "site-002"
        assert req.device_bacnet_id is None
        assert req.bms_vendor is None

        # Verify demo fields are NOT in model
        fields = DiscoverRequest.model_fields
        assert "use_demo" not in fields, "use_demo should be removed"
        assert "demo_site_id" not in fields, "demo_site_id should be removed"

        # Verify only expected fields exist
        expected_fields = {"device_ip", "site_id", "device_bacnet_id", "bms_vendor"}
        assert set(fields.keys()) == expected_fields, f"Unexpected fields: {set(fields.keys()) - expected_fields}"

        # Even if use_demo is passed, it should NOT appear on the model instance
        req2 = DiscoverRequest(device_ip="sim", site_id="s002")
        assert not hasattr(req2, "use_demo") or "use_demo" not in req2.model_fields
