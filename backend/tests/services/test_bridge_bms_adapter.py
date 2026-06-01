"""Unit tests for BridgeBmsAdapter."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.simbiot.bms_adapter import BmsConnectionConfig, BmsWriteRequest
from app.services.simbiot.bridge_bms_adapter import BridgeBmsAdapter, bridge_adapter_from_connection_config


@pytest.fixture
def adapter():
    return BridgeBmsAdapter(
        base_url="http://10.99.0.1:8080",
        token="test-token-abc",
        timeout_seconds=5.0,
    )


@pytest.fixture
def connection_config() -> BmsConnectionConfig:
    return BmsConnectionConfig(
        site_id="site-002",
        source_type="bridge",
    )


class TestBridgeBmsAdapterIdentity:
    def test_adapter_id(self, adapter):
        assert adapter.adapter_id == "bridge"

    def test_capabilities_reads_true(self, adapter):
        assert adapter.capabilities.supports_reads is True

    def test_capabilities_writes_false(self, adapter):
        assert adapter.capabilities.supports_writes is False

    def test_capabilities_subscriptions_false(self, adapter):
        assert adapter.capabilities.supports_subscriptions is False

    def test_capabilities_discovery_true(self, adapter):
        assert adapter.capabilities.supports_device_discovery is True


class TestBridgeBmsAdapterConnect:
    @pytest.mark.asyncio
    async def test_connect_success_on_200(self, adapter, connection_config):
        mock_resp = MagicMock()
        mock_resp.status_code = 200

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value = mock_client

            status = await adapter.connect(connection_config)

        assert status.connected is True
        assert status.site_id == "site-002"
        assert status.source_type == "bridge"

    @pytest.mark.asyncio
    async def test_connect_failure_on_non_200(self, adapter, connection_config):
        mock_resp = MagicMock()
        mock_resp.status_code = 503

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value = mock_client

            status = await adapter.connect(connection_config)

        assert status.connected is False
        assert "503" in status.message

    @pytest.mark.asyncio
    async def test_connect_failure_on_network_error(self, adapter, connection_config):
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.get = AsyncMock(side_effect=Exception("Connection refused"))
            mock_client_cls.return_value = mock_client

            status = await adapter.connect(connection_config)

        assert status.connected is False


class TestBridgeBmsAdapterDiscovery:
    @pytest.mark.asyncio
    async def test_discover_devices_returns_bridge_descriptor(self, adapter, connection_config):
        adapter._site_id = "site-002"
        devices = await adapter.discover_devices()

        assert len(devices) == 1
        assert devices[0].protocol == "bridge"
        assert "site-002" in devices[0].device_id

    @pytest.mark.asyncio
    async def test_discover_points_returns_point_descriptors(self, adapter, connection_config):
        adapter._site_id = "site-002"
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = MagicMock(
            return_value={
                "objects": [
                    {"object_id": "CH-1.ChwSupplyTemp", "object_name": "Chiller Supply", "point_type": "sensor"},
                    {"object_id": "AHU-B1.FanSpeed", "object_name": "Fan Speed", "point_type": "analog_value"},
                ]
            }
        )

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value = mock_client

            points = await adapter.discover_points("bridge-site-002")

        assert len(points) == 2
        ids = {p.point_id for p in points}
        assert "CH-1.ChwSupplyTemp" in ids

    @pytest.mark.asyncio
    async def test_discover_points_returns_empty_on_error(self, adapter):
        adapter._site_id = "site-002"
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.get = AsyncMock(side_effect=Exception("timeout"))
            mock_client_cls.return_value = mock_client

            points = await adapter.discover_points("bridge-site-002")

        assert points == []


class TestBridgeBmsAdapterReadWrite:
    @pytest.mark.asyncio
    async def test_write_point_always_returns_false(self, adapter):
        req = BmsWriteRequest(device_id="bridge-site-002", point_id="AHU.setpoint", value=22.0)
        result = await adapter.write_point(req)
        assert result is False

    @pytest.mark.asyncio
    async def test_subscribe_raises_not_implemented(self, adapter):
        with pytest.raises(NotImplementedError):
            await adapter.subscribe_points("bridge-site-002", ["point-1"])

    @pytest.mark.asyncio
    async def test_read_point_returns_bad_quality_on_error(self, adapter):
        adapter._site_id = "site-002"
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.get = AsyncMock(side_effect=Exception("timeout"))
            mock_client_cls.return_value = mock_client

            point = await adapter.read_point("bridge-site-002", "CH-1.ChwSupplyTemp")

        assert point.quality == "bad"
        assert point.value is None


class TestBridgeAdapterFactory:
    def test_factory_returns_adapter_with_valid_config(self):
        adapter = bridge_adapter_from_connection_config(
            "site-002",
            {"base_url": "http://10.99.0.1:8080", "token": "abc123"},
        )
        assert adapter is not None
        assert isinstance(adapter, BridgeBmsAdapter)

    def test_factory_returns_none_missing_base_url(self):
        adapter = bridge_adapter_from_connection_config(
            "site-002",
            {"token": "abc123"},
        )
        assert adapter is None

    def test_factory_returns_none_missing_token(self):
        adapter = bridge_adapter_from_connection_config(
            "site-002",
            {"base_url": "http://10.99.0.1:8080"},
        )
        assert adapter is None

    def test_factory_returns_none_empty_config(self):
        adapter = bridge_adapter_from_connection_config("site-002", {})
        assert adapter is None
