"""Tests for Niagara BACnet/IP Device Adapter.

Verifies integration of NiagaraBACnetClient with SENTINEL's
device abstraction layer via NiagaraBACnetAdapter.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.device import (
    Device,
    DeviceEquipment,
    DeviceLocation,
    DevicePoint,
    DeviceStatus,
    DeviceType,
    PointType,
    ProtocolType,
)
from app.services.niagara.bacnet_adapter import (
    BACNET_TO_POINT_TYPE,
    NiagaraBACnetAdapter,
    _bacnet_type_writable,
    _discovered_point_to_device_point,
)
from app.services.niagara.bacnet_client import (
    BACnetException,
    BACnetReadError,
    BACnetTimeoutError,
    BACnetWriteError,
    DiscoveredPoint,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def bacnet_device() -> Device:
    """Create a Device configured for BACnet protocol."""
    return Device(
        id="S002-AHU-L1-001",
        name="Test AHU",
        device_type=DeviceType.HVAC,
        protocol=ProtocolType.BACNET,
        site_id="site-002",
        device_location=DeviceLocation(
            building="Sandton Tower",
            floor="L1",
            zone="A",
            room="MR1",
            description="Level 1 Zone A Mechanical Room",
        ),
        equipment=DeviceEquipment(
            manufacturer="Tridium",
            model="JACE-8000",
        ),
        metadata={"bacnet_device_id": 1234},
        points={
            "chw_supply_temp": DevicePoint(
                name="chw_supply_temp",
                point_type=PointType.ANALOG_INPUT,
                description="Chilled water supply temperature",
                unit="degC",
                writable=False,
                metadata={
                    "bacnet_object_type": "analogInput",
                    "bacnet_instance": 0,
                },
            ),
            "zone_setpoint": DevicePoint(
                name="zone_setpoint",
                point_type=PointType.ANALOG_OUTPUT,
                description="Zone temperature setpoint",
                unit="degC",
                min_value=16.0,
                max_value=28.0,
                default_value=22.0,
                writable=True,
                metadata={
                    "bacnet_object_type": "analogOutput",
                    "bacnet_instance": 1,
                },
            ),
            "fan_status": DevicePoint(
                name="fan_status",
                point_type=PointType.BINARY_INPUT,
                description="Fan running status",
                unit="",
                writable=False,
                metadata={
                    "bacnet_object_type": "binaryInput",
                    "bacnet_instance": 0,
                },
            ),
        },
    )


@pytest.fixture
def mock_client():
    """Create a mock BACnet client."""
    mock = MagicMock()
    mock.is_running = True
    mock._bac0_unavailable = False
    mock.read_point = AsyncMock()
    mock.write_point = AsyncMock(return_value=True)
    mock.read_point_list = AsyncMock(return_value=[])
    mock.list_subscriptions.return_value = []
    mock.cancel_subscription = AsyncMock(return_value=True)
    mock.start = AsyncMock()
    return mock


@pytest.fixture
def adapter(bacnet_device, mock_client):
    """Create a NiagaraBACnetAdapter with mocked client."""
    with patch("app.services.niagara.bacnet_adapter.get_bacnet_client", return_value=mock_client):
        adpt = NiagaraBACnetAdapter(bacnet_device)
    adpt._client = mock_client
    return adpt


# ---------------------------------------------------------------------------
# Adapter Lifecycle
# ---------------------------------------------------------------------------


class TestAdapterLifecycle:
    """Tests for connect/disconnect lifecycle."""

    @pytest.mark.asyncio
    async def test_connect_starts_client_if_needed(self, adapter, mock_client):
        mock_client.is_running = False
        mock_client.read_point.return_value = "Test AHU"

        result = await adapter._protocol_connect()

        assert result is True
        mock_client.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_verifies_device_reachable(self, adapter, mock_client):
        mock_client.read_point.return_value = "Test AHU"

        result = await adapter._protocol_connect()

        assert result is True
        mock_client.read_point.assert_called_once_with(1234, "device", 1234, property_name="objectName")

    @pytest.mark.asyncio
    async def test_connect_returns_false_on_timeout(self, adapter, mock_client):
        mock_client.read_point.side_effect = BACnetTimeoutError("Timed out")

        result = await adapter._protocol_connect()

        assert result is False

    @pytest.mark.asyncio
    async def test_connect_returns_true_on_other_bacnet_errors(self, adapter, mock_client):
        """Device may not support objectName read but still be functional."""
        mock_client.read_point.side_effect = BACnetException("Not supported")

        result = await adapter._protocol_connect()

        assert result is True

    @pytest.mark.asyncio
    async def test_disconnect_cancels_subscriptions(self, adapter, mock_client):

        mock_sub = MagicMock()
        mock_sub.device_id = 1234
        mock_sub.subscription_id = "sub-1"
        mock_client.list_subscriptions.return_value = [mock_sub]

        await adapter._protocol_disconnect()

        mock_client.cancel_subscription.assert_called_once_with("sub-1")


# ---------------------------------------------------------------------------
# Read Operations
# ---------------------------------------------------------------------------


class TestAdapterRead:
    """Tests for reading point values."""

    @pytest.mark.asyncio
    async def test_read_analog_value(self, adapter, mock_client):
        mock_client.read_point.return_value = 22.5

        result = await adapter._protocol_read("chw_supply_temp")

        assert result.point_name == "chw_supply_temp"
        assert result.value == 22.5
        assert result.quality == "good"
        mock_client.read_point.assert_called_once_with(
            device_id=1234,
            object_type="analogInput",
            instance=0,
        )

    @pytest.mark.asyncio
    async def test_read_binary_value(self, adapter, mock_client):
        mock_client.read_point.return_value = True

        result = await adapter._protocol_read("fan_status")

        assert result.value is True
        assert result.quality == "good"

    @pytest.mark.asyncio
    async def test_read_timeout_returns_uncertain(self, adapter, mock_client):
        mock_client.read_point.side_effect = BACnetTimeoutError("Timed out")

        result = await adapter._protocol_read("chw_supply_temp")

        assert result.value is None
        assert result.quality == "uncertain"

    @pytest.mark.asyncio
    async def test_read_error_returns_bad(self, adapter, mock_client):
        mock_client.read_point.side_effect = BACnetReadError("Read failed")

        result = await adapter._protocol_read("chw_supply_temp")

        assert result.value is None
        assert result.quality == "bad"

    @pytest.mark.asyncio
    async def test_read_missing_point_raises(self, adapter, mock_client):
        with pytest.raises(ValueError, match="not found"):
            await adapter._protocol_read("nonexistent_point")

    @pytest.mark.asyncio
    async def test_read_missing_bacnet_metadata_raises(self, adapter, mock_client):
        # Add a point without BACnet metadata
        adapter.device.points["broken_point"] = DevicePoint(
            name="broken_point",
            point_type=PointType.ANALOG_INPUT,
            metadata={},  # No bacnet_object_type / bacnet_instance
        )

        with pytest.raises(ValueError, match="missing BACnet metadata"):
            await adapter._protocol_read("broken_point")


# ---------------------------------------------------------------------------
# Write Operations
# ---------------------------------------------------------------------------


class TestAdapterWrite:
    """Tests for writing point values."""

    @pytest.mark.asyncio
    async def test_write_with_priority(self, adapter, mock_client):
        result = await adapter._protocol_write("zone_setpoint", 23.0, priority=8)

        assert result is True
        mock_client.write_point.assert_called_once_with(
            device_id=1234,
            object_type="analogOutput",
            instance=1,
            value=23.0,
            priority=8,
        )

    @pytest.mark.asyncio
    async def test_write_custom_priority(self, adapter, mock_client):
        await adapter._protocol_write("zone_setpoint", 24.0, priority=1)

        mock_client.write_point.assert_called_once_with(
            device_id=1234,
            object_type="analogOutput",
            instance=1,
            value=24.0,
            priority=1,
        )

    @pytest.mark.asyncio
    async def test_write_missing_point_raises(self, adapter, mock_client):
        with pytest.raises(ValueError, match="not found"):
            await adapter._protocol_write("nonexistent", 42.0, priority=8)

    @pytest.mark.asyncio
    async def test_write_propagates_bacnet_errors(self, adapter, mock_client):
        mock_client.write_point.side_effect = BACnetWriteError("Write rejected")

        with pytest.raises(BACnetWriteError):
            await adapter._protocol_write("zone_setpoint", 30.0, priority=8)


# ---------------------------------------------------------------------------
# Point Scanning
# ---------------------------------------------------------------------------


class TestAdapterScan:
    """Tests for point discovery/scanning."""

    @pytest.mark.asyncio
    async def test_scan_points(self, adapter, mock_client):
        mock_client.read_point_list.return_value = [
            DiscoveredPoint(
                object_type="analogInput",
                instance=0,
                name="temp_sensor",
                units="degC",
                writable=False,
            ),
            DiscoveredPoint(
                object_type="analogOutput",
                instance=1,
                name="setpoint",
                units="degC",
                writable=True,
            ),
        ]

        points = await adapter.scan_points()

        assert len(points) == 2
        assert "temp_sensor" in points
        assert "setpoint" in points
        assert points["temp_sensor"].point_type == PointType.ANALOG_INPUT
        assert points["setpoint"].writable is True

    @pytest.mark.asyncio
    async def test_scan_failure_returns_existing_points(self, adapter, mock_client):
        mock_client.read_point_list.side_effect = BACnetException("Scan failed")

        points = await adapter.scan_points()

        # Should return existing device points
        assert "chw_supply_temp" in points
        assert "zone_setpoint" in points


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


class TestAdapterStatus:
    """Tests for device status checking."""

    @pytest.mark.asyncio
    async def test_status_online(self, adapter, mock_client):
        mock_client.read_point.return_value = "Test AHU"

        status = await adapter.get_status()

        assert status == DeviceStatus.ONLINE

    @pytest.mark.asyncio
    async def test_status_offline_on_timeout(self, adapter, mock_client):
        mock_client.read_point.side_effect = BACnetTimeoutError("Timed out")

        status = await adapter.get_status()

        assert status == DeviceStatus.OFFLINE

    @pytest.mark.asyncio
    async def test_status_fault_on_error(self, adapter, mock_client):
        mock_client.read_point.side_effect = BACnetException("Error")

        status = await adapter.get_status()

        assert status == DeviceStatus.FAULT


# ---------------------------------------------------------------------------
# BACnet device ID extraction
# ---------------------------------------------------------------------------


class TestBACnetDeviceId:
    """Tests for bacnet_device_id property."""

    def test_extracts_from_metadata(self, adapter):
        assert adapter.bacnet_device_id == 1234

    def test_caches_device_id(self, adapter):
        _ = adapter.bacnet_device_id
        _ = adapter.bacnet_device_id
        # Should not re-extract - cached after first access
        assert adapter._bacnet_device_id == 1234

    def test_raises_if_missing(self, mock_client):
        device = Device(
            id="no-bacnet-id",
            name="Test",
            device_type=DeviceType.HVAC,
            protocol=ProtocolType.BACNET,
            site_id="site-001",
            device_location=DeviceLocation(building="Test", floor="L1", zone="A", room="MR1", description="Test"),
            equipment=DeviceEquipment(manufacturer="Test", model="Test"),
            metadata={},  # No bacnet_device_id
        )
        with patch("app.services.niagara.bacnet_adapter.get_bacnet_client", return_value=mock_client):
            adpt = NiagaraBACnetAdapter(device)
            adpt._client = mock_client

        with pytest.raises(BACnetException, match="bacnet_device_id"):
            _ = adpt.bacnet_device_id


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------


class TestUtilityFunctions:
    """Tests for mapping/conversion utility functions."""

    def test_bacnet_to_point_type_mapping(self):
        assert BACNET_TO_POINT_TYPE["analogInput"] == PointType.ANALOG_INPUT
        assert BACNET_TO_POINT_TYPE["binaryOutput"] == PointType.BINARY_OUTPUT
        assert BACNET_TO_POINT_TYPE["multiStateValue"] == PointType.MULTISTATE_VALUE

    def test_writable_types(self):
        assert _bacnet_type_writable("analogOutput") is True
        assert _bacnet_type_writable("binaryOutput") is True
        assert _bacnet_type_writable("analogInput") is False
        assert _bacnet_type_writable("binaryInput") is False

    def test_discovered_point_conversion(self):
        dp = DiscoveredPoint(
            object_type="analogInput",
            instance=5,
            name="temp",
            description="Temperature sensor",
            units="degC",
            writable=False,
        )

        point = _discovered_point_to_device_point(dp)

        assert point.name == "temp"
        assert point.point_type == PointType.ANALOG_INPUT
        assert point.unit == "degC"
        assert point.writable is False
        assert point.metadata["bacnet_object_type"] == "analogInput"
        assert point.metadata["bacnet_instance"] == 5

    def test_discovered_point_unnamed(self):
        dp = DiscoveredPoint(
            object_type="analogValue",
            instance=42,
        )

        point = _discovered_point_to_device_point(dp)

        assert point.name == "analogValue_42"
