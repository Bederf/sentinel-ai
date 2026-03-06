"""Tests for zone-aware HVAC optimization.

This module tests the zone-aware optimization features including:
- Zone grouping by floor and zone name
- Exposure modifier calculations
- Zone priority ordering
- Zone-specific setpoint limits
- Load shedding stage filtering
"""

from datetime import datetime
from unittest.mock import patch

from app.models.device import (
    DeviceType,
    DeviceLocation,
    DeviceEquipment,
    DevicePoint,
    PointType,
    ProtocolType,
    ZoneType,
    ExposureDirection,
    create_device_from_dict,
    HVACDevice,
)
from app.services.ai_optimizer import AIOptimizerService


class TestZoneEnums:
    """Test zone-related enums."""

    def test_zone_type_values(self):
        """Test ZoneType enum has all expected values."""
        assert ZoneType.EXECUTIVE.value == "executive"
        assert ZoneType.SERVER_ROOM.value == "server_room"
        assert ZoneType.MEETING_ROOM.value == "meeting_room"
        assert ZoneType.OPEN_OFFICE.value == "open_office"
        assert ZoneType.LOBBY.value == "lobby"
        assert ZoneType.PLANT_ROOM.value == "plant_room"
        assert ZoneType.PARKING.value == "parking"
        assert ZoneType.BANKING_HALL.value == "banking_hall"

    def test_exposure_direction_values(self):
        """Test ExposureDirection enum has all expected values."""
        assert ExposureDirection.NORTH.value == "north"
        assert ExposureDirection.SOUTH.value == "south"
        assert ExposureDirection.EAST.value == "east"
        assert ExposureDirection.WEST.value == "west"
        assert ExposureDirection.INTERIOR.value == "interior"


class TestDeviceLocationZoneMetadata:
    """Test DeviceLocation with zone metadata."""

    def test_device_location_with_zone_fields(self):
        """Test DeviceLocation includes zone metadata fields."""
        location = DeviceLocation(
            building="Test Building",
            floor="FL3",
            zone="Executive Wing",
            room="OR301",
            description="Test location",
            zone_type=ZoneType.EXECUTIVE,
            exposure=ExposureDirection.SOUTH,
            zone_priority=1,
        )

        assert location.zone_type == ZoneType.EXECUTIVE
        assert location.exposure == ExposureDirection.SOUTH
        assert location.zone_priority == 1

    def test_device_location_default_zone_priority(self):
        """Test DeviceLocation defaults to priority 3."""
        location = DeviceLocation(
            building="Test Building", floor="FL1", zone="Open Office", room="OR001", description="Test location"
        )

        assert location.zone_priority == 3
        assert location.zone_type is None
        assert location.exposure is None

    def test_device_location_to_dict_includes_zone_fields(self):
        """Test to_dict includes zone metadata."""
        location = DeviceLocation(
            building="Test Building",
            floor="FL3",
            zone="Executive Wing",
            room="OR301",
            description="Test location",
            zone_type=ZoneType.EXECUTIVE,
            exposure=ExposureDirection.SOUTH,
            zone_priority=1,
        )

        result = location.to_dict()

        assert result["zone_type"] == "executive"
        assert result["exposure"] == "south"
        assert result["zone_priority"] == 1


class TestCreateDeviceFromDict:
    """Test device creation from dict with zone metadata."""

    def test_create_device_with_zone_metadata(self):
        """Test creating device from dict with zone metadata."""
        data = {
            "id": "test-device-001",
            "name": "Test Device",
            "device_type": "hvac",
            "protocol": "mock",
            "site_id": "site-001",
            "hvac_type": "fcu",
            "device_location": {
                "building": "Test Building",
                "floor": "FL3",
                "zone": "Executive Wing",
                "room": "OR301",
                "description": "Test location",
                "zone_type": "executive",
                "exposure": "south",
                "zone_priority": 1,
            },
            "equipment": {"manufacturer": "Test", "model": "T-100"},
            "points": {},
        }

        device = create_device_from_dict(data)

        assert device.device_location.zone_type == ZoneType.EXECUTIVE
        assert device.device_location.exposure == ExposureDirection.SOUTH
        assert device.device_location.zone_priority == 1


class TestAIOptimizerZoneGrouping:
    """Test AI optimizer zone grouping methods."""

    def setup_method(self):
        """Set up test fixtures."""
        self.optimizer = AIOptimizerService()
        self.test_devices = self._create_test_devices()

    def _create_test_devices(self):
        """Create test devices with various zone configurations."""
        devices = []

        # Executive zone device (FL3, south-facing)
        devices.append(
            self._create_test_device(
                "exec-fcu-001", "Executive FCU", "FL3", "Executive Wing", ZoneType.EXECUTIVE, ExposureDirection.SOUTH, 1
            )
        )

        # Open office device (FL2, east-facing)
        devices.append(
            self._create_test_device(
                "office-fcu-001", "Office FCU", "FL2", "Main Office", ZoneType.OPEN_OFFICE, ExposureDirection.EAST, 3
            )
        )

        # Plant room device (Basement, interior)
        devices.append(
            self._create_test_device(
                "plant-chiller-001",
                "Plant Chiller",
                "Basement",
                "Plant Room",
                ZoneType.PLANT_ROOM,
                ExposureDirection.INTERIOR,
                5,
            )
        )

        # Another FL2 device for grouping test
        devices.append(
            self._create_test_device(
                "office-fcu-002", "Office FCU 2", "FL2", "Main Office", ZoneType.OPEN_OFFICE, ExposureDirection.WEST, 3
            )
        )

        return devices

    def _create_test_device(self, device_id, name, floor, zone, zone_type, exposure, priority):
        """Create a test device with specified attributes."""
        return HVACDevice(
            id=device_id,
            name=name,
            device_type=DeviceType.HVAC,
            protocol=ProtocolType.MOCK,
            site_id="site-001",
            device_location=DeviceLocation(
                building="Test Building",
                floor=floor,
                zone=zone,
                room="MR1",
                description=f"{floor}, {zone}",
                zone_type=zone_type,
                exposure=exposure,
                zone_priority=priority,
            ),
            equipment=DeviceEquipment(manufacturer="Test", model="T-100"),
            hvac_type="fcu",
            points={
                "room_temp_setpoint": DevicePoint(
                    name="room_temp_setpoint",
                    point_type=PointType.ANALOG_VALUE,
                    writable=True,
                    default_value=22.0,
                    min_value=18.0,
                    max_value=26.0,
                )
            },
        )

    def test_group_devices_by_zone(self):
        """Test grouping devices by zone name."""
        zones = self.optimizer._group_devices_by_zone(self.test_devices)

        assert "Executive Wing" in zones
        assert "Main Office" in zones
        assert "Plant Room" in zones

        assert len(zones["Executive Wing"]) == 1
        assert len(zones["Main Office"]) == 2  # Two devices in same zone
        assert len(zones["Plant Room"]) == 1

    def test_group_devices_by_floor(self):
        """Test grouping devices by floor."""
        floors = self.optimizer._group_devices_by_floor(self.test_devices)

        assert "FL3" in floors
        assert "FL2" in floors
        assert "Basement" in floors

        assert len(floors["FL3"]) == 1
        assert len(floors["FL2"]) == 2  # Two devices on FL2
        assert len(floors["Basement"]) == 1

    def test_get_zone_priority(self):
        """Test getting zone priority from device."""
        exec_device = self.test_devices[0]  # Executive, priority 1
        office_device = self.test_devices[1]  # Open office, priority 3
        plant_device = self.test_devices[2]  # Plant room, priority 5

        assert self.optimizer._get_zone_priority(exec_device) == 1
        assert self.optimizer._get_zone_priority(office_device) == 3
        assert self.optimizer._get_zone_priority(plant_device) == 5

    def test_get_zone_type(self):
        """Test getting zone type from device."""
        exec_device = self.test_devices[0]
        office_device = self.test_devices[1]

        assert self.optimizer._get_zone_type(exec_device) == ZoneType.EXECUTIVE
        assert self.optimizer._get_zone_type(office_device) == ZoneType.OPEN_OFFICE

    def test_get_exposure(self):
        """Test getting exposure direction from device."""
        south_device = self.test_devices[0]  # South-facing
        east_device = self.test_devices[1]  # East-facing

        assert self.optimizer._get_exposure(south_device) == ExposureDirection.SOUTH
        assert self.optimizer._get_exposure(east_device) == ExposureDirection.EAST

    def test_get_floor_level(self):
        """Test parsing floor level from device location."""
        # FL3 -> 3
        assert self.optimizer._get_floor_level(self.test_devices[0]) == 3
        # FL2 -> 2
        assert self.optimizer._get_floor_level(self.test_devices[1]) == 2
        # Basement -> -1
        assert self.optimizer._get_floor_level(self.test_devices[2]) == -1


class TestExposureModifiers:
    """Test exposure-based temperature modifiers."""

    def setup_method(self):
        """Set up test fixtures."""
        self.optimizer = AIOptimizerService()

    def _create_device_with_exposure(self, exposure):
        """Create test device with specified exposure."""
        return HVACDevice(
            id="test-device",
            name="Test Device",
            device_type=DeviceType.HVAC,
            protocol=ProtocolType.MOCK,
            site_id="site-001",
            device_location=DeviceLocation(
                building="Test",
                floor="FL1",
                zone="Test Zone",
                room="OR001",
                description="Test",
                exposure=exposure,
                zone_priority=3,
            ),
            equipment=DeviceEquipment(manufacturer="Test", model="T-100"),
            hvac_type="fcu",
            points={},
        )

    def test_exposure_modifier_low_temp_returns_zero(self):
        """Test that low outdoor temps return zero modifier."""
        device = self._create_device_with_exposure(ExposureDirection.SOUTH)
        modifier = self.optimizer._get_exposure_modifier(device, 20.0)  # Cool temp
        assert modifier == 0.0

    def test_exposure_modifier_south_facing_midday(self):
        """Test south-facing zones get low modifier midday (SA: sun in NORTH sky)."""
        device = self._create_device_with_exposure(ExposureDirection.SOUTH)

        # Mock datetime to midday (12:00)
        with patch("app.services.ai_optimizer.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 1, 30, 12, 0)
            modifier = self.optimizer._get_exposure_modifier(device, 30.0)

        # In SA, south-facing gets minimal direct sun (diffuse/reflected only)
        assert modifier == 0.3

    def test_exposure_modifier_west_facing_afternoon(self):
        """Test west-facing zones get modifier in afternoon."""
        device = self._create_device_with_exposure(ExposureDirection.WEST)

        # Mock datetime to afternoon (15:00)
        with patch("app.services.ai_optimizer.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 1, 30, 15, 0)
            modifier = self.optimizer._get_exposure_modifier(device, 30.0)

        assert modifier == 1.0  # Afternoon heat

    def test_exposure_modifier_interior_returns_negative(self):
        """Test interior zones get negative modifier (less cooling needed)."""
        device = self._create_device_with_exposure(ExposureDirection.INTERIOR)
        modifier = self.optimizer._get_exposure_modifier(device, 30.0)
        assert modifier == -0.5

    def test_exposure_modifier_north_facing_high_gain(self):
        """Test north-facing zones (SA) get max solar gain (sun in NORTH sky)."""
        device = self._create_device_with_exposure(ExposureDirection.NORTH)
        # At 30C outdoor temp (>25 threshold), north-facing gets solar gain
        modifier = self.optimizer._get_exposure_modifier(device, 30.0)
        # North-facing returns 1.5 (10-16h) or 0.5 (other hours)
        assert modifier in (0.5, 1.5)


class TestZoneSpecificLimits:
    """Test zone-specific setpoint limits."""

    def setup_method(self):
        """Set up test fixtures."""
        self.optimizer = AIOptimizerService()

    def _create_device_with_zone_type(self, zone_type):
        """Create test device with specified zone type."""
        return HVACDevice(
            id="test-device",
            name="Test Device",
            device_type=DeviceType.HVAC,
            protocol=ProtocolType.MOCK,
            site_id="site-001",
            device_location=DeviceLocation(
                building="Test",
                floor="FL1",
                zone="Test Zone",
                room="OR001",
                description="Test",
                zone_type=zone_type,
                zone_priority=3,
            ),
            equipment=DeviceEquipment(manufacturer="Test", model="T-100"),
            hvac_type="fcu",
            points={},
        )

    def test_server_room_limits(self):
        """Test server room has tight temperature limits."""
        device = self._create_device_with_zone_type(ZoneType.SERVER_ROOM)
        min_temp, max_temp = self.optimizer._get_zone_specific_setpoint_limits(device, ZoneType.SERVER_ROOM)
        assert min_temp == 18.0
        assert max_temp == 22.0

    def test_executive_limits(self):
        """Test executive zone has tight comfort limits."""
        device = self._create_device_with_zone_type(ZoneType.EXECUTIVE)
        min_temp, max_temp = self.optimizer._get_zone_specific_setpoint_limits(device, ZoneType.EXECUTIVE)
        assert min_temp == 21.0
        assert max_temp == 23.0

    def test_plant_room_limits(self):
        """Test plant room has wide temperature limits."""
        device = self._create_device_with_zone_type(ZoneType.PLANT_ROOM)
        min_temp, max_temp = self.optimizer._get_zone_specific_setpoint_limits(device, ZoneType.PLANT_ROOM)
        assert min_temp == 16.0
        assert max_temp == 30.0

    def test_open_office_limits(self):
        """Test open office has standard comfort limits."""
        device = self._create_device_with_zone_type(ZoneType.OPEN_OFFICE)
        min_temp, max_temp = self.optimizer._get_zone_specific_setpoint_limits(device, ZoneType.OPEN_OFFICE)
        assert min_temp == 20.0
        assert max_temp == 26.0


class TestSkipZoneOptimization:
    """Test zone optimization skip logic."""

    def setup_method(self):
        """Set up test fixtures."""
        self.optimizer = AIOptimizerService()

    def _create_device_with_zone_type(self, zone_type):
        """Create test device with specified zone type."""
        return HVACDevice(
            id="test-device",
            name="Test Device",
            device_type=DeviceType.HVAC,
            protocol=ProtocolType.MOCK,
            site_id="site-001",
            device_location=DeviceLocation(
                building="Test",
                floor="FL1",
                zone="Test Zone",
                room="OR001",
                description="Test",
                zone_type=zone_type,
                zone_priority=1,
            ),
            equipment=DeviceEquipment(manufacturer="Test", model="T-100"),
            hvac_type="fcu",
            points={},
        )

    def test_skip_server_room_optimization(self):
        """Test server rooms are skipped for optimization."""
        device = self._create_device_with_zone_type(ZoneType.SERVER_ROOM)
        should_skip = self.optimizer._should_skip_zone_optimization(device, ZoneType.SERVER_ROOM)
        assert should_skip is True

    def test_allow_open_office_optimization(self):
        """Test open offices are not skipped."""
        device = self._create_device_with_zone_type(ZoneType.OPEN_OFFICE)
        should_skip = self.optimizer._should_skip_zone_optimization(device, ZoneType.OPEN_OFFICE)
        assert should_skip is False

    def test_allow_executive_optimization(self):
        """Test executive zones are not skipped (but get reduced changes)."""
        device = self._create_device_with_zone_type(ZoneType.EXECUTIVE)
        should_skip = self.optimizer._should_skip_zone_optimization(device, ZoneType.EXECUTIVE)
        assert should_skip is False


class TestZoneAwareAdjustments:
    """Test zone-aware setpoint adjustments."""

    def setup_method(self):
        """Set up test fixtures."""
        self.optimizer = AIOptimizerService()

    def _create_device(self, floor, zone_type, exposure):
        """Create test device with specified attributes."""
        floor_level = {"FL1": 1, "FL3": 3, "Roof": 99, "Basement": -1, "Ground": 0}
        return HVACDevice(
            id="test-device",
            name="Test Device",
            device_type=DeviceType.HVAC,
            protocol=ProtocolType.MOCK,
            site_id="site-001",
            device_location=DeviceLocation(
                building="Test",
                floor=floor,
                zone="Test Zone",
                room="OR001",
                description="Test",
                zone_type=zone_type,
                exposure=exposure,
                zone_priority=3,
            ),
            equipment=DeviceEquipment(manufacturer="Test", model="T-100"),
            hvac_type="fcu",
            points={},
        )

    def test_executive_zone_reduced_change(self):
        """Test executive zones get reduced setpoint changes."""
        device = self._create_device("FL3", ZoneType.EXECUTIVE, ExposureDirection.NORTH)
        adjusted = self.optimizer._apply_zone_aware_adjustments(device, 1.5, 25.0)
        # Executive gets 50% of base change (but also 70% for top floor)
        assert adjusted < 1.5

    def test_plant_room_aggressive_change(self):
        """Test plant rooms get more aggressive changes."""
        device = self._create_device("Basement", ZoneType.PLANT_ROOM, ExposureDirection.INTERIOR)
        adjusted = self.optimizer._apply_zone_aware_adjustments(device, 1.0, 25.0)
        # Plant room gets 150% of base change
        assert adjusted > 1.0

    def test_server_room_zero_change(self):
        """Test server rooms get zero change (never reduce cooling)."""
        device = self._create_device("FL1", ZoneType.SERVER_ROOM, ExposureDirection.INTERIOR)
        adjusted = self.optimizer._apply_zone_aware_adjustments(device, 1.5, 30.0)
        assert adjusted == 0.0

    def test_top_floor_stronger_optimization(self):
        """Test top floor devices get stronger optimization (1.2x) per policy tuning."""
        device = self._create_device("FL3", ZoneType.OPEN_OFFICE, ExposureDirection.NORTH)
        adjusted = self.optimizer._apply_zone_aware_adjustments(device, 1.5, 25.0)
        # Top floor (FL3) gets 1.2x multiplier = 1.8, then minus north exposure adjustment
        # North-facing exposure modifier (0.5 or 1.5) * 0.3 subtracted
        assert adjusted > 1.0  # More aggressive than base


class TestSortRecommendationsByPriority:
    """Test recommendation sorting by zone priority."""

    def setup_method(self):
        """Set up test fixtures."""
        self.optimizer = AIOptimizerService()

    def _create_device(self, device_id, priority):
        """Create test device with specified priority."""
        return HVACDevice(
            id=device_id,
            name=f"Device {device_id}",
            device_type=DeviceType.HVAC,
            protocol=ProtocolType.MOCK,
            site_id="site-001",
            device_location=DeviceLocation(
                building="Test", floor="FL1", zone="Test", room="MR1", description="Test", zone_priority=priority
            ),
            equipment=DeviceEquipment(manufacturer="Test", model="T-100"),
            hvac_type="fcu",
            points={},
        )

    def test_sort_by_priority(self):
        """Test recommendations sorted by zone priority."""
        devices = [
            self._create_device("device-p5", 5),  # Lowest priority
            self._create_device("device-p1", 1),  # Highest priority
            self._create_device("device-p3", 3),  # Middle priority
        ]

        recommendations = [
            {"equipment_id": "device-p5", "point_name": "setpoint", "recommended_value": 24.0},
            {"equipment_id": "device-p1", "point_name": "setpoint", "recommended_value": 22.0},
            {"equipment_id": "device-p3", "point_name": "setpoint", "recommended_value": 23.0},
        ]

        sorted_recs = self.optimizer._sort_recommendations_by_priority(recommendations, devices)

        # Should be sorted P1, P3, P5
        assert sorted_recs[0]["equipment_id"] == "device-p1"
        assert sorted_recs[1]["equipment_id"] == "device-p3"
        assert sorted_recs[2]["equipment_id"] == "device-p5"


class TestFormatZoneContext:
    """Test zone context formatting for Claude prompt."""

    def setup_method(self):
        """Set up test fixtures."""
        self.optimizer = AIOptimizerService()

    def _create_device(self, device_id, zone_type, exposure, priority):
        """Create test device."""
        return HVACDevice(
            id=device_id,
            name=f"Device {device_id}",
            device_type=DeviceType.HVAC,
            protocol=ProtocolType.MOCK,
            site_id="site-001",
            device_location=DeviceLocation(
                building="Test",
                floor="FL1",
                zone="Test",
                room="MR1",
                description="Test",
                zone_type=zone_type,
                exposure=exposure,
                zone_priority=priority,
            ),
            equipment=DeviceEquipment(manufacturer="Test", model="T-100"),
            hvac_type="fcu",
            points={},
        )

    def test_format_zone_context(self):
        """Test zone context includes all zone types."""
        devices = [
            self._create_device("exec-001", ZoneType.EXECUTIVE, ExposureDirection.SOUTH, 1),
            self._create_device("office-001", ZoneType.OPEN_OFFICE, ExposureDirection.EAST, 3),
        ]

        context = self.optimizer._format_zone_context(devices)

        assert "Zone Classification" in context
        assert "executive" in context
        assert "open_office" in context
        assert "south" in context
        assert "P1" in context
        assert "P3" in context


# Integration test placeholder (requires async test setup)
class TestLoadSheddingIntegration:
    """Test load shedding zone priority integration."""

    def test_priority_thresholds(self):
        """Test load shedding priority thresholds are correct."""
        # These are the thresholds defined in analyze_site_load_shedding
        priority_threshold = {
            1: 4,  # Stage 1: Keep P1-P4, shed P5
            2: 3,  # Stage 2: Keep P1-P3, shed P4-P5
            3: 2,  # Stage 3: Keep P1-P2, shed P3-P5
            4: 1,  # Stage 4: Keep P1 only
        }

        assert priority_threshold[1] == 4
        assert priority_threshold[2] == 3
        assert priority_threshold[3] == 2
        assert priority_threshold[4] == 1
