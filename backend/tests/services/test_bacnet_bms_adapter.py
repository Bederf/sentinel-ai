from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.simbiot import BmsConnectionConfig, BmsWriteRequest
from app.services.simbiot.bacnet_bms_adapter import BacnetBmsAdapter


@pytest.mark.unit
class TestBacnetBmsAdapter:
    @pytest.mark.asyncio
    async def test_connect_discovers_status_and_devices(self):
        mock_client = MagicMock()
        mock_client.is_running = False
        mock_client._bac0_unavailable = False
        mock_client.start = AsyncMock(side_effect=lambda: setattr(mock_client, "is_running", True))
        mock_client.discover_devices = AsyncMock(
            return_value=[
                MagicMock(
                    device_id=1234,
                    object_name="AHU Controller",
                    ip_address="192.168.1.100:47808",
                    vendor_name="Siemens",
                    model_name="PXC",
                    firmware_version="1.0",
                )
            ]
        )

        with patch("app.services.simbiot.bacnet_bms_adapter.get_bacnet_client", return_value=mock_client):
            adapter = BacnetBmsAdapter()
            status = await adapter.connect(
                BmsConnectionConfig(
                    site_id="site-002",
                    source_type="bacnet",
                    host="192.168.1.100",
                )
            )
            devices = await adapter.discover_devices()

        assert status.connected is True
        assert status.metadata["host"] == "192.168.1.100"
        assert devices[0].device_id == "1234"
        assert devices[0].display_name == "AHU Controller"
        assert devices[0].address == "192.168.1.100:47808"

    @pytest.mark.asyncio
    async def test_discover_points_reads_metadata(self):
        mock_point = MagicMock(object_type="analogValue", instance=7, writable=True)
        mock_client = MagicMock()
        mock_client.is_running = True
        mock_client._bac0_unavailable = False
        mock_client.read_point_list = AsyncMock(return_value=[mock_point])
        mock_client.read_point = AsyncMock(side_effect=["CHW_SP", "Supply setpoint", "degC"])

        with patch("app.services.simbiot.bacnet_bms_adapter.get_bacnet_client", return_value=mock_client):
            adapter = BacnetBmsAdapter()
            await adapter.connect(BmsConnectionConfig(site_id="site-002", source_type="bacnet"))
            points = await adapter.discover_points("1234")

        assert len(points) == 1
        assert points[0].point_id == "analogValue:7"
        assert points[0].point_name == "CHW_SP"
        assert points[0].unit == "degC"
        assert points[0].metadata["description"] == "Supply setpoint"

    @pytest.mark.asyncio
    async def test_read_and_write_point_parse_bacnet_point_ids(self):
        mock_client = MagicMock()
        mock_client.is_running = True
        mock_client._bac0_unavailable = False
        mock_client.read_point = AsyncMock(side_effect=[12.5, "degC"])
        mock_client.write_point = AsyncMock(return_value=True)

        with patch("app.services.simbiot.bacnet_bms_adapter.get_bacnet_client", return_value=mock_client):
            adapter = BacnetBmsAdapter()
            await adapter.connect(BmsConnectionConfig(site_id="site-002", source_type="bacnet"))
            value = await adapter.read_point("1234", "analogValue:9")
            success = await adapter.write_point(
                BmsWriteRequest(
                    device_id="1234",
                    point_id="analogValue:9",
                    value=11.0,
                    priority=8,
                )
            )

        assert value.value == 12.5
        assert value.unit == "degC"
        assert value.metadata["object_type"] == "analogValue"
        assert value.metadata["instance"] == 9
        assert success is True
        mock_client.write_point.assert_awaited_once_with(
            device_id=1234,
            object_type="analogValue",
            instance=9,
            value=11.0,
            priority=8,
        )
