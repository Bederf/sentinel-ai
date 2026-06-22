"""Tests for KnxBmsAdapter — SIMBIOT BmsAdapter wrapper for KNX."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.services.simbiot import BmsConnectionConfig, BmsWriteRequest
from app.services.simbiot.knx_bms_adapter import KnxBmsAdapter, _is_emergency_group


def _make_config(group_addresses=None, host="192.168.1.100", port=3671):
    return BmsConnectionConfig(
        site_id="site-002",
        source_type="knx",
        host=host,
        port=port,
        timeout_seconds=5.0,
        metadata={
            "group_addresses": group_addresses or {},
        },
    )


def _sample_group_addresses(with_emergency=False):
    gas = {
        "zone_temp": {
            "read_address": "1/1/1",
            "write_address": "1/1/1",
            "dpt": "9.001",
            "description": "Zone 1 Temperature",
            "unit": "°C",
        },
        "light_level": {
            "read_address": "1/2/1",
            "write_address": "1/2/1",
            "dpt": "5.001",
            "description": "Dimming Level",
            "unit": "%",
        },
    }
    if with_emergency:
        gas["fire_alarm"] = {
            "read_address": "2/0/1",
            "write_address": "2/0/1",
            "dpt": "1.001",
            "description": "Fire Alarm Status",
            "unit": "",
        }
    return gas


# -------------------------------------------------------------------------
# Capabilities
# -------------------------------------------------------------------------
class TestCapabilities:
    def test_adapter_id(self):
        adapter = KnxBmsAdapter()
        assert adapter.adapter_id == "knx"

    def test_capabilities(self):
        adapter = KnxBmsAdapter()
        caps = adapter.capabilities
        assert caps.supports_device_discovery is False
        assert caps.supports_point_discovery is True
        assert caps.supports_reads is True
        assert caps.supports_writes is True
        assert caps.supports_subscriptions is False
        assert caps.supports_history is False


# -------------------------------------------------------------------------
# Emergency group detection
# -------------------------------------------------------------------------
class TestEmergencyGroupDetection:
    @pytest.mark.parametrize(
        "description,is_emergency",
        [
            ("Zone 1 Temperature", False),
            ("Emergency Lighting", True),
            ("Fire Alarm Zone A", True),
            ("Evacuation Route Lighting", True),
            ("HVAC Normal Mode", False),
            ("Panic Button Status", True),
        ],
    )
    def test_emergency_pattern_detection(self, description, is_emergency):
        meta = {"description": description}
        assert _is_emergency_group(meta) == is_emergency


# -------------------------------------------------------------------------
# Connection tests
# -------------------------------------------------------------------------
class TestConnection:
    @pytest.mark.asyncio
    async def test_connect_success(self):
        mock_client = AsyncMock()
        mock_client.connect = AsyncMock(return_value=True)

        adapter = KnxBmsAdapter()
        with patch(
            "app.services.knx.knx_client.get_knx_client",
            return_value=mock_client,
        ):
            status = await adapter.connect(_make_config())

        assert status.connected is True
        assert status.status == "connected"
        assert "KNX gateway connected" in status.message

    @pytest.mark.asyncio
    async def test_connect_failure(self):
        mock_client = AsyncMock()
        mock_client.connect = AsyncMock(return_value=False)

        adapter = KnxBmsAdapter()
        with patch(
            "app.services.knx.knx_client.get_knx_client",
            return_value=mock_client,
        ):
            status = await adapter.connect(_make_config())

        assert status.connected is False
        assert status.status == "disconnected"

    @pytest.mark.asyncio
    async def test_connect_exception(self):
        adapter = KnxBmsAdapter()
        with patch(
            "app.services.knx.knx_client.get_knx_client",
            side_effect=ImportError("xknx not installed"),
        ):
            status = await adapter.connect(_make_config())

        assert status.connected is False
        assert status.status == "error"

    @pytest.mark.asyncio
    async def test_disconnect(self):
        mock_client = AsyncMock()
        mock_client.connect = AsyncMock(return_value=True)
        mock_client.disconnect = AsyncMock()

        adapter = KnxBmsAdapter()
        with patch(
            "app.services.knx.knx_client.get_knx_client",
            return_value=mock_client,
        ):
            await adapter.connect(_make_config())
            await adapter.disconnect()

        assert adapter._connected is False
        assert adapter._client is None


# -------------------------------------------------------------------------
# Discovery tests
# -------------------------------------------------------------------------
class TestDiscovery:
    @pytest.mark.asyncio
    async def test_discover_devices_returns_single_gateway(self):
        adapter = KnxBmsAdapter()
        adapter._config = _make_config()
        devices = await adapter.discover_devices()

        assert len(devices) == 1
        assert devices[0].protocol == "knx"
        assert "knx-gateway" in devices[0].device_id

    @pytest.mark.asyncio
    async def test_discover_points_from_group_addresses(self):
        adapter = KnxBmsAdapter()
        adapter._group_addresses = _sample_group_addresses()

        points = await adapter.discover_points("knx-gateway-site-002")

        assert len(points) == 2
        point_names = {p.point_name for p in points}
        assert "zone_temp" in point_names
        assert "light_level" in point_names

    @pytest.mark.asyncio
    async def test_discover_points_empty_map(self):
        adapter = KnxBmsAdapter()
        adapter._group_addresses = {}

        points = await adapter.discover_points("knx-gateway")
        assert points == []

    @pytest.mark.asyncio
    async def test_discover_points_emergency_not_writable(self):
        adapter = KnxBmsAdapter()
        adapter._group_addresses = _sample_group_addresses(with_emergency=True)

        points = await adapter.discover_points("knx-gateway")
        fire_point = next(p for p in points if p.point_id == "fire_alarm")
        assert fire_point.writable is False


# -------------------------------------------------------------------------
# Read tests
# -------------------------------------------------------------------------
class TestRead:
    @pytest.mark.asyncio
    async def test_read_point_success(self):
        mock_client = AsyncMock()
        mock_client.read_group_address = AsyncMock(return_value=21.5)

        adapter = KnxBmsAdapter()
        adapter._connected = True
        adapter._client = mock_client
        adapter._group_addresses = _sample_group_addresses()

        result = await adapter.read_point("knx-gateway", "zone_temp")

        assert result.device_id == "knx-gateway"
        assert result.point_id == "zone_temp"
        assert result.value == 21.5
        assert result.unit == "°C"
        mock_client.read_group_address.assert_called_once_with("1/1/1", "9.001")

    @pytest.mark.asyncio
    async def test_read_point_not_found_raises(self):
        mock_client = AsyncMock()
        adapter = KnxBmsAdapter()
        adapter._connected = True
        adapter._client = mock_client
        adapter._group_addresses = _sample_group_addresses()

        with pytest.raises(ValueError, match="Point not found"):
            await adapter.read_point("knx-gateway", "nonexistent")

    @pytest.mark.asyncio
    async def test_read_point_not_connected_raises(self):
        adapter = KnxBmsAdapter()
        with pytest.raises(ConnectionError, match="not connected"):
            await adapter.read_point("knx-gateway", "zone_temp")


# -------------------------------------------------------------------------
# Write tests
# -------------------------------------------------------------------------
class TestWrite:
    @pytest.mark.asyncio
    async def test_write_point_success(self):
        mock_client = AsyncMock()
        mock_client.write_group_address = AsyncMock(return_value=True)

        adapter = KnxBmsAdapter()
        adapter._connected = True
        adapter._client = mock_client
        adapter._group_addresses = _sample_group_addresses()

        request = BmsWriteRequest(
            device_id="knx-gateway",
            point_id="light_level",
            value=75.0,
        )
        result = await adapter.write_point(request)

        assert result is True
        mock_client.write_group_address.assert_called_once_with("1/2/1", 75.0, "5.001", request.priority)

    @pytest.mark.asyncio
    async def test_write_point_not_found_returns_false(self):
        mock_client = AsyncMock()
        adapter = KnxBmsAdapter()
        adapter._connected = True
        adapter._client = mock_client
        adapter._group_addresses = _sample_group_addresses()

        request = BmsWriteRequest(
            device_id="knx-gateway",
            point_id="nonexistent",
            value=1,
        )
        result = await adapter.write_point(request)
        assert result is False

    @pytest.mark.asyncio
    async def test_write_to_emergency_group_returns_false(self):
        """Emergency/fire group writes must be blocked — safety check must not regress."""
        mock_client = AsyncMock()
        mock_client.write_group_address = AsyncMock(return_value=True)

        adapter = KnxBmsAdapter()
        adapter._connected = True
        adapter._client = mock_client
        adapter._group_addresses = _sample_group_addresses(with_emergency=True)

        request = BmsWriteRequest(
            device_id="knx-gateway",
            point_id="fire_alarm",
            value=True,
        )
        result = await adapter.write_point(request)

        assert result is False
        mock_client.write_group_address.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_write_point_not_connected_raises(self):
        adapter = KnxBmsAdapter()
        request = BmsWriteRequest(
            device_id="knx-gateway",
            point_id="zone_temp",
            value=22.0,
        )
        with pytest.raises(ConnectionError, match="not connected"):
            await adapter.write_point(request)


# -------------------------------------------------------------------------
# Status tests
# -------------------------------------------------------------------------
class TestStatus:
    @pytest.mark.asyncio
    async def test_get_status_connected(self):
        mock_client = AsyncMock()
        mock_client.gateway_health_check = AsyncMock(return_value={"status": "healthy", "gateway": "192.168.1.100"})

        adapter = KnxBmsAdapter()
        adapter._config = _make_config()
        adapter._connected = True
        adapter._client = mock_client

        status = await adapter.get_status()

        assert status.connected is True
        assert status.status == "connected"

    @pytest.mark.asyncio
    async def test_get_status_disconnected(self):
        adapter = KnxBmsAdapter()
        adapter._config = _make_config()
        adapter._connected = False
        adapter._client = None

        status = await adapter.get_status()

        assert status.connected is False
        assert status.status == "disconnected"
