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

    def test_capabilities_writes_false_by_default(self, adapter):
        assert adapter.capabilities.supports_writes is False

    def test_capabilities_writes_true_when_enabled(self):
        adapter = BridgeBmsAdapter(
            base_url="http://10.99.0.1:8080",
            token="test-token-abc",
            timeout_seconds=5.0,
            write_enabled=True,
        )
        assert adapter.capabilities.supports_writes is True

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
    async def test_discover_points_falls_back_to_points_endpoint(self, adapter, connection_config):
        adapter._site_id = "site-002"

        objects_resp = MagicMock()
        objects_resp.raise_for_status = MagicMock(side_effect=Exception("not found"))

        points_resp = MagicMock()
        points_resp.raise_for_status = MagicMock()
        points_resp.json = MagicMock(
            return_value={
                "points": [
                    {
                        "point_id": "S002-MTR-B01.power",
                        "point_name": "Meter Power",
                        "point_type": "sensor",
                        "unit": "kW",
                        "equipment_id": "S002-MTR-B01",
                        "object_type": "analogInput",
                        "instance": 1076,
                    }
                ]
            }
        )

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.get = AsyncMock(side_effect=[objects_resp, points_resp])
            mock_client_cls.return_value = mock_client

            points = await adapter.discover_points("bridge-site-002")

        assert len(points) == 1
        assert points[0].point_id == "S002-MTR-B01.power"
        assert points[0].metadata["bacnet_instance"] == 1076
        assert points[0].metadata["source_endpoint"] == "points"

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
    async def test_write_point_returns_false_when_disabled(self, adapter):
        req = BmsWriteRequest(device_id="bridge-site-002", point_id="AHU.setpoint", value=22.0)
        result = await adapter.write_point(req)
        assert result is False

    @pytest.mark.asyncio
    async def test_write_point_posts_to_bridge_when_enabled(self):
        adapter = BridgeBmsAdapter(
            base_url="http://10.99.0.1:8080",
            token="test-token-abc",
            timeout_seconds=5.0,
            write_enabled=True,
        )
        adapter._site_id = "site-002"
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b'{"success": true}'
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = MagicMock(return_value={"success": True})

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value = mock_client

            req = BmsWriteRequest(device_id="S002-AHU-B01", point_id="S002-AHU-B1-001.sat_setpoint", value=16.0)
            result = await adapter.write_point(req)

        assert result is True
        mock_client.post.assert_awaited_once_with(
            "http://10.99.0.1:8080/api/sites/site-002/write",
            headers={"Authorization": "Bearer test-token-abc"},
            json={
                "object_id": "S002-AHU-B1-001.sat_setpoint",
                "value": 16.0,
                "priority": 14,
                "requested_by": "system",
                "approval_id": "",
            },
        )

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
            {"base_url": "http://10.99.0.1:8080", "token": "abc123", "supports_writes": True, "write_enabled": True},
        )
        assert adapter is not None
        assert isinstance(adapter, BridgeBmsAdapter)
        assert adapter.capabilities.supports_writes is True

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
