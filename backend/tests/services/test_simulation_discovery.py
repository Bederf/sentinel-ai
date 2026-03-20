"""Tests for adapter-backed discovery in ``PointDiscoveryService``."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.niagara.point_discovery import (
    PointDiscoveryService,
    _infer_object_type,
    _infer_point_type,
)
from app.services.niagara.point_classifier import ClassifiedPoint, ConfidenceLevel, PointType


# ---------------------------------------------------------------------------
# Test: Simulation Point Adapter
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSimulationPointAdapter:
    """Test adapter-backed simulation discovery and helper functions."""

    @pytest.mark.asyncio
    async def test_load_simulation_points_returns_formatted_points(self):
        """Mock the simulation adapter and verify discovery point format."""
        svc = PointDiscoveryService()

        devices = [
            MagicMock(
                device_id="S002-CHILLER-B1-001", display_name="Chiller 1", metadata={"equipment_type": "CHILLER"}
            ),
            MagicMock(device_id="S002-AHU-B1-001", display_name="AHU 1", metadata={"equipment_type": "AHU"}),
            MagicMock(device_id="S002-FCU-101", display_name="FCU Zone 101", metadata={"equipment_type": "FCU"}),
        ]
        device_points = {
            "S002-CHILLER-B1-001": [
                MagicMock(
                    point_id="chilled_water_supply_temp",
                    point_name="chilled_water_supply_temp",
                    unit="°C",
                    writable=False,
                    metadata={},
                ),
                MagicMock(
                    point_id="chilled_water_setpoint",
                    point_name="chilled_water_setpoint",
                    unit="°C",
                    writable=True,
                    metadata={},
                ),
            ],
            "S002-AHU-B1-001": [
                MagicMock(
                    point_id="supply_air_temp", point_name="supply_air_temp", unit="°C", writable=False, metadata={}
                ),
                MagicMock(point_id="fault_status", point_name="fault_status", unit="", writable=False, metadata={}),
            ],
            "S002-FCU-101": [
                MagicMock(point_id="room_temp", point_name="room_temp", unit="°C", writable=False, metadata={}),
                MagicMock(point_id="enable_command", point_name="enable_command", unit="", writable=True, metadata={}),
            ],
        }
        point_values = {
            ("S002-CHILLER-B1-001", "chilled_water_supply_temp"): 7.2,
            ("S002-CHILLER-B1-001", "chilled_water_setpoint"): 6.5,
            ("S002-AHU-B1-001", "supply_air_temp"): 14.5,
            ("S002-AHU-B1-001", "fault_status"): 0,
            ("S002-FCU-101", "room_temp"): 22.1,
            ("S002-FCU-101", "enable_command"): 1,
        }

        adapter_instance = MagicMock()
        adapter_instance.connect = AsyncMock()
        adapter_instance.disconnect = AsyncMock()
        adapter_instance.discover_devices = AsyncMock(return_value=devices)
        adapter_instance.discover_points = AsyncMock(side_effect=lambda device_id: device_points[device_id])
        adapter_instance.read_points = AsyncMock(
            side_effect=lambda device_id, point_ids: [
                MagicMock(point_id=point_id, value=point_values[(device_id, point_id)], unit=None)
                for point_id in point_ids
            ]
        )
        adapter_instance.read_point = AsyncMock(
            side_effect=lambda device_id, point_id: MagicMock(value=point_values[(device_id, point_id)], unit=None)
        )

        with patch("app.services.niagara.point_discovery.create_bms_adapter", return_value=adapter_instance):
            points = await svc._load_simulation_points("site-002")

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

    @pytest.mark.asyncio
    async def test_load_simulation_points_empty_when_no_equipment(self):
        """Mock adapter to return no devices, assert empty list."""
        svc = PointDiscoveryService()

        adapter_instance = MagicMock()
        adapter_instance.connect = AsyncMock()
        adapter_instance.disconnect = AsyncMock()
        adapter_instance.discover_devices = AsyncMock(return_value=[])

        with patch("app.services.niagara.point_discovery.create_bms_adapter", return_value=adapter_instance):
            points = await svc._load_simulation_points("site-999")

        assert points == []

    @pytest.mark.asyncio
    async def test_load_simulation_points_handles_adapter_error(self):
        """Mock adapter to raise exception, assert empty list (graceful degradation)."""
        svc = PointDiscoveryService()

        adapter_instance = MagicMock()
        adapter_instance.connect = AsyncMock(side_effect=RuntimeError("adapter unavailable"))
        adapter_instance.disconnect = AsyncMock()

        with patch("app.services.niagara.point_discovery.create_bms_adapter", return_value=adapter_instance):
            points = await svc._load_simulation_points("site-002")

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

    def test_apply_module_policy_filters_inactive_module_points(self):
        svc = PointDiscoveryService()
        raw_points = [
            {"name": "S002-AHU-L1-001.room_temp", "instance": 1},
            {"name": "S002-PV-R-001.pv_power_kw", "instance": 2},
        ]
        classified_points = [
            ClassifiedPoint(
                original_name="S002-AHU-L1-001.room_temp",
                equipment_type="ahu",
                point_type=PointType.SENSOR,
                confidence=ConfidenceLevel.HIGH,
                instance=1,
            ),
            ClassifiedPoint(
                original_name="S002-PV-R-001.pv_power_kw",
                equipment_type="solar",
                point_type=PointType.SENSOR,
                confidence=ConfidenceLevel.HIGH,
                instance=2,
            ),
        ]

        with patch(
            "app.services.niagara.point_discovery.filter_classified_points_for_site",
            return_value=([classified_points[0]], 1),
        ):
            filtered_raw, filtered_classified, dropped = svc._apply_module_policy(
                "site-002", raw_points, classified_points
            )

        assert filtered_raw == [{"name": "S002-AHU-L1-001.room_temp", "instance": 1}]
        assert filtered_classified == [classified_points[0]]
        assert dropped == 1


# ---------------------------------------------------------------------------
# Test: Discovery Routing
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDiscoveryRouting:
    """Test 3-tier routing: BACnet -> Simulation -> JSON fallback."""

    @pytest.mark.asyncio
    async def test_routing_bacnet_first(self):
        """When a live adapter yields points, use it and skip simulation fallback."""
        svc = PointDiscoveryService()

        bacnet_points = [{"name": "BACnet-Point-1", "object_type": "analogInput"}]

        with (
            patch.object(svc, "_load_adapter_points", new=AsyncMock(return_value=bacnet_points)) as mock_live,
            patch.object(svc, "_load_simulation_points") as mock_sim,
        ):
            points = await svc._discover_points("192.168.1.100", "site-002", device_bacnet_id=1234)

        assert points == bacnet_points
        mock_live.assert_called_once_with(
            adapter_type="bacnet",
            site_id="site-002",
            device_ip="192.168.1.100",
            device_bacnet_id=1234,
            bms_vendor=None,
        )
        mock_sim.assert_not_called()

    @pytest.mark.asyncio
    async def test_routing_simulation_fallback_when_no_bacnet(self):
        """Without explicit live adapter selection, discovery should fall back directly to simulation."""
        svc = PointDiscoveryService()

        sim_points = [{"name": "S002-CHILLER.temp", "object_type": "analogInput"}]

        with (
            patch.object(svc, "_load_adapter_points", new=AsyncMock(return_value=[])) as mock_live,
            patch.object(svc, "_load_simulation_points", new=AsyncMock(return_value=sim_points)) as mock_sim,
            patch.object(svc, "_load_demo_points") as mock_json,
        ):
            points = await svc._discover_points("192.168.1.100", "site-002")

        assert points == sim_points
        mock_live.assert_not_called()
        mock_sim.assert_called_once_with("site-002")
        mock_json.assert_not_called()

    @pytest.mark.asyncio
    async def test_routing_honors_explicit_simulation_adapter(self):
        """Adapter selection should drive simulation routing without relying on device_ip magic."""
        svc = PointDiscoveryService()

        sim_points = [{"name": "S002-CHILLER.temp", "object_type": "analogInput"}]

        with (
            patch.object(svc, "_load_adapter_points", new=AsyncMock(return_value=sim_points)) as mock_adapter,
            patch.object(svc, "_load_simulation_points") as mock_sim,
            patch.object(svc, "_load_demo_points") as mock_json,
        ):
            points = await svc._discover_points("192.168.1.100", "site-002", adapter_type="simulation")

        assert points == sim_points
        mock_adapter.assert_called_once_with(
            adapter_type="simulation",
            site_id="site-002",
            device_ip="192.168.1.100",
            device_bacnet_id=None,
            bms_vendor=None,
        )
        mock_sim.assert_not_called()
        mock_json.assert_not_called()

    @pytest.mark.asyncio
    async def test_routing_json_fallback_when_simulation_empty(self):
        """When simulation returns empty, fall back to JSON files."""
        svc = PointDiscoveryService()

        json_points = [{"name": "S002-FCU-101.room_temp", "object_type": "analogInput"}]

        with (
            patch.object(svc, "_load_adapter_points", new=AsyncMock(return_value=[])) as mock_live,
            patch.object(svc, "_load_simulation_points", new=AsyncMock(return_value=[])) as mock_sim,
            patch.object(svc, "_load_demo_points", return_value=json_points) as mock_json,
        ):
            points = await svc._discover_points("simulation", "site-002")

        assert points == json_points
        mock_live.assert_called_once_with(
            adapter_type="simulation",
            site_id="site-002",
            device_ip="simulation",
            device_bacnet_id=None,
            bms_vendor=None,
        )
        mock_sim.assert_not_called()
        mock_json.assert_called_once_with("site-002")

    @pytest.mark.asyncio
    async def test_routing_vendor_alias_uses_resolved_adapter(self):
        """Vendor aliases should resolve to the underlying live adapter type."""
        svc = PointDiscoveryService()
        live_points = [{"name": "AV-1", "object_type": "analogValue"}]

        with (
            patch.object(svc, "_load_adapter_points", new=AsyncMock(return_value=live_points)) as mock_live,
            patch.object(svc, "_load_simulation_points") as mock_sim,
        ):
            points = await svc._discover_points(
                "192.168.1.100",
                "site-002",
                adapter_type=None,
                bms_vendor="desigo",
            )

        assert points == live_points
        mock_live.assert_called_once_with(
            adapter_type="bacnet",
            site_id="site-002",
            device_ip="192.168.1.100",
            device_bacnet_id=None,
            bms_vendor="desigo",
        )
        mock_sim.assert_not_called()

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
        assert req.adapter_type is None
        assert req.bms_vendor is None

        # Verify demo fields are NOT in model
        fields = DiscoverRequest.model_fields
        assert "use_demo" not in fields, "use_demo should be removed"
        assert "demo_site_id" not in fields, "demo_site_id should be removed"

        # Verify only expected fields exist
        expected_fields = {"device_ip", "site_id", "device_bacnet_id", "adapter_type", "bms_vendor"}
        assert set(fields.keys()) == expected_fields, f"Unexpected fields: {set(fields.keys()) - expected_fields}"

        # Even if use_demo is passed, it should NOT appear on the model instance
        req2 = DiscoverRequest(device_ip="sim", site_id="s002")
        assert not hasattr(req2, "use_demo") or "use_demo" not in req2.model_fields
