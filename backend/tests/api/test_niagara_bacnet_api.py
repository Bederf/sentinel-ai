"""Tests for Niagara BACnet/IP API endpoints and models.

Verifies the REST API layer functions, Pydantic models, and BACnet
model validation for device discovery, point read/write, and
COV subscription management.

Note: TestClient is incompatible with httpx 0.28.x + starlette 0.36.x,
so API endpoint functions are tested directly with mocked dependencies.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.niagara.bacnet_client import (
    BACnetException,
    BACnetReadError,
    BACnetTimeoutError,
    BACnetWriteError,
    COVSubscription,
    DiscoveredDevice,
    DiscoveredPoint,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_bacnet_client():
    """Create a mock BACnet client with common properties."""
    mock = MagicMock()
    mock.is_running = True
    mock.get_status.return_value = {
        "started": True,
        "port": 47808,
        "ip": None,
        "active_subscriptions": 0,
        "cached_devices": 0,
    }
    mock.list_subscriptions.return_value = []
    return mock


# ---------------------------------------------------------------------------
# Status endpoint
# ---------------------------------------------------------------------------

class TestBACnetStatusEndpoint:
    """Tests for get_bacnet_status endpoint function."""

    @pytest.mark.asyncio
    async def test_status_returns_client_info(self, mock_bacnet_client):
        from app.api.niagara_bacnet import get_bacnet_status

        with patch("app.api.niagara_bacnet.get_bacnet_client", return_value=mock_bacnet_client):
            result = await get_bacnet_status()

        assert result.started is True
        assert result.port == 47808
        assert result.active_subscriptions == 0

    @pytest.mark.asyncio
    async def test_status_when_stopped(self, mock_bacnet_client):
        from app.api.niagara_bacnet import get_bacnet_status

        mock_bacnet_client.get_status.return_value = {
            "started": False,
            "port": 47808,
            "ip": None,
            "active_subscriptions": 0,
            "cached_devices": 0,
        }

        with patch("app.api.niagara_bacnet.get_bacnet_client", return_value=mock_bacnet_client):
            result = await get_bacnet_status()

        assert result.started is False


# ---------------------------------------------------------------------------
# Device Discovery
# ---------------------------------------------------------------------------

class TestDeviceDiscoveryEndpoint:
    """Tests for discover_devices endpoint function."""

    @pytest.mark.asyncio
    async def test_discover_returns_devices(self, mock_bacnet_client):
        from app.api.niagara_bacnet import discover_devices
        from app.models.niagara import BACnetDiscoverRequest

        mock_devices = [
            DiscoveredDevice(device_id=1000, ip_address="192.168.1.100", vendor_name="Tridium"),
            DiscoveredDevice(device_id=2000, ip_address="192.168.1.101", vendor_name="Tridium"),
        ]
        mock_bacnet_client.discover_devices = AsyncMock(return_value=mock_devices)

        with patch("app.api.niagara_bacnet.get_bacnet_client", return_value=mock_bacnet_client):
            result = await discover_devices(BACnetDiscoverRequest(timeout=5.0))

        assert result.count == 2
        assert result.devices[0].device_id == 1000
        assert result.devices[0].vendor_name == "Tridium"

    @pytest.mark.asyncio
    async def test_discover_empty_network(self, mock_bacnet_client):
        from app.api.niagara_bacnet import discover_devices
        from app.models.niagara import BACnetDiscoverRequest

        mock_bacnet_client.discover_devices = AsyncMock(return_value=[])

        with patch("app.api.niagara_bacnet.get_bacnet_client", return_value=mock_bacnet_client):
            result = await discover_devices(BACnetDiscoverRequest())

        assert result.count == 0
        assert result.devices == []

    @pytest.mark.asyncio
    async def test_discover_client_not_started(self, mock_bacnet_client):
        from app.api.niagara_bacnet import discover_devices
        from app.models.niagara import BACnetDiscoverRequest
        from fastapi import HTTPException

        mock_bacnet_client.is_running = False

        with patch("app.api.niagara_bacnet.get_bacnet_client", return_value=mock_bacnet_client):
            with pytest.raises(HTTPException) as exc_info:
                await discover_devices(BACnetDiscoverRequest())
            assert exc_info.value.status_code == 503

    @pytest.mark.asyncio
    async def test_discover_timeout_returns_empty(self, mock_bacnet_client):
        from app.api.niagara_bacnet import discover_devices
        from app.models.niagara import BACnetDiscoverRequest

        mock_bacnet_client.discover_devices = AsyncMock(
            side_effect=BACnetTimeoutError("Discovery timed out")
        )

        with patch("app.api.niagara_bacnet.get_bacnet_client", return_value=mock_bacnet_client):
            result = await discover_devices(BACnetDiscoverRequest())

        assert result.count == 0


# ---------------------------------------------------------------------------
# Point Discovery
# ---------------------------------------------------------------------------

class TestPointDiscoveryEndpoint:
    """Tests for discover_device_points endpoint function."""

    @pytest.mark.asyncio
    async def test_discover_points(self, mock_bacnet_client):
        from app.api.niagara_bacnet import discover_device_points

        mock_points = [
            DiscoveredPoint(object_type="analogInput", instance=0, name="temp", writable=False),
            DiscoveredPoint(object_type="analogOutput", instance=1, name="setpoint", writable=True),
        ]
        mock_bacnet_client.read_point_list = AsyncMock(return_value=mock_points)

        with patch("app.api.niagara_bacnet.get_bacnet_client", return_value=mock_bacnet_client):
            result = await discover_device_points(device_id=1000, object_type=None, use_cache=True)

        assert result.device_id == 1000
        assert result.count == 2
        assert result.points[0].object_type == "analogInput"
        assert result.points[1].writable is True

    @pytest.mark.asyncio
    async def test_discover_points_with_type_filter(self, mock_bacnet_client):
        from app.api.niagara_bacnet import discover_device_points

        mock_points = [
            DiscoveredPoint(object_type="analogValue", instance=0),
        ]
        mock_bacnet_client.read_point_list = AsyncMock(return_value=mock_points)

        with patch("app.api.niagara_bacnet.get_bacnet_client", return_value=mock_bacnet_client):
            result = await discover_device_points(device_id=1000, object_type="analogValue", use_cache=True)

        mock_bacnet_client.read_point_list.assert_called_once_with(
            device_id=1000,
            object_types=["analogValue"],
            use_cache=True,
        )

    @pytest.mark.asyncio
    async def test_discover_points_client_not_started(self, mock_bacnet_client):
        from app.api.niagara_bacnet import discover_device_points
        from fastapi import HTTPException

        mock_bacnet_client.is_running = False

        with patch("app.api.niagara_bacnet.get_bacnet_client", return_value=mock_bacnet_client):
            with pytest.raises(HTTPException) as exc_info:
                await discover_device_points(device_id=1000, object_type=None, use_cache=True)
            assert exc_info.value.status_code == 503


# ---------------------------------------------------------------------------
# Point Read
# ---------------------------------------------------------------------------

class TestPointReadEndpoint:
    """Tests for read_point endpoint function."""

    @pytest.mark.asyncio
    async def test_read_point_value(self, mock_bacnet_client):
        from app.api.niagara_bacnet import read_point

        mock_bacnet_client.read_point = AsyncMock(return_value=72.5)

        with patch("app.api.niagara_bacnet.get_bacnet_client", return_value=mock_bacnet_client):
            result = await read_point(
                device_id=1000,
                object_type="analogValue",
                instance=0,
                property_name="presentValue",
            )

        assert result.device_id == 1000
        assert result.object_type == "analogValue"
        assert result.instance == 0
        assert result.value == 72.5
        assert result.property_name == "presentValue"

    @pytest.mark.asyncio
    async def test_read_point_custom_property(self, mock_bacnet_client):
        from app.api.niagara_bacnet import read_point

        mock_bacnet_client.read_point = AsyncMock(return_value="Zone Temp")

        with patch("app.api.niagara_bacnet.get_bacnet_client", return_value=mock_bacnet_client):
            result = await read_point(
                device_id=1000,
                object_type="analogValue",
                instance=0,
                property_name="objectName",
            )

        assert result.property_name == "objectName"
        assert result.value == "Zone Temp"

    @pytest.mark.asyncio
    async def test_read_point_timeout(self, mock_bacnet_client):
        from app.api.niagara_bacnet import read_point
        from fastapi import HTTPException

        mock_bacnet_client.read_point = AsyncMock(
            side_effect=BACnetTimeoutError("Timed out")
        )

        with patch("app.api.niagara_bacnet.get_bacnet_client", return_value=mock_bacnet_client):
            with pytest.raises(HTTPException) as exc_info:
                await read_point(
                    device_id=1000,
                    object_type="analogValue",
                    instance=0,
                    property_name="presentValue",
                )
            assert exc_info.value.status_code == 504

    @pytest.mark.asyncio
    async def test_read_point_read_error(self, mock_bacnet_client):
        from app.api.niagara_bacnet import read_point
        from fastapi import HTTPException

        mock_bacnet_client.read_point = AsyncMock(
            side_effect=BACnetReadError("Read failed")
        )

        with patch("app.api.niagara_bacnet.get_bacnet_client", return_value=mock_bacnet_client):
            with pytest.raises(HTTPException) as exc_info:
                await read_point(
                    device_id=1000,
                    object_type="analogValue",
                    instance=0,
                    property_name="presentValue",
                )
            assert exc_info.value.status_code == 502

    @pytest.mark.asyncio
    async def test_read_point_not_started(self, mock_bacnet_client):
        from app.api.niagara_bacnet import read_point
        from fastapi import HTTPException

        mock_bacnet_client.is_running = False

        with patch("app.api.niagara_bacnet.get_bacnet_client", return_value=mock_bacnet_client):
            with pytest.raises(HTTPException) as exc_info:
                await read_point(
                    device_id=1000,
                    object_type="analogValue",
                    instance=0,
                    property_name="presentValue",
                )
            assert exc_info.value.status_code == 503


# ---------------------------------------------------------------------------
# Point Write
# ---------------------------------------------------------------------------

class TestPointWriteEndpoint:
    """Tests for write_point endpoint function."""

    @pytest.mark.asyncio
    async def test_write_point_value(self, mock_bacnet_client):
        from app.api.niagara_bacnet import write_point
        from app.models.niagara import BACnetPointWriteRequest

        mock_bacnet_client.write_point = AsyncMock(return_value=True)

        with patch("app.api.niagara_bacnet.get_bacnet_client", return_value=mock_bacnet_client):
            result = await write_point(
                device_id=1000,
                object_type="analogOutput",
                instance=1,
                request=BACnetPointWriteRequest(value=22.5, priority=8),
            )

        assert result.success is True
        assert result.value == 22.5
        assert result.priority == 8

    @pytest.mark.asyncio
    async def test_write_point_default_priority(self, mock_bacnet_client):
        from app.api.niagara_bacnet import write_point
        from app.models.niagara import BACnetPointWriteRequest

        mock_bacnet_client.write_point = AsyncMock(return_value=True)

        with patch("app.api.niagara_bacnet.get_bacnet_client", return_value=mock_bacnet_client):
            result = await write_point(
                device_id=1000,
                object_type="analogOutput",
                instance=1,
                request=BACnetPointWriteRequest(value=22.5),
            )

        mock_bacnet_client.write_point.assert_called_once_with(
            device_id=1000,
            object_type="analogOutput",
            instance=1,
            value=22.5,
            priority=8,
        )

    @pytest.mark.asyncio
    async def test_write_point_error(self, mock_bacnet_client):
        from app.api.niagara_bacnet import write_point
        from app.models.niagara import BACnetPointWriteRequest
        from fastapi import HTTPException

        mock_bacnet_client.write_point = AsyncMock(
            side_effect=BACnetWriteError("Write rejected")
        )

        with patch("app.api.niagara_bacnet.get_bacnet_client", return_value=mock_bacnet_client):
            with pytest.raises(HTTPException) as exc_info:
                await write_point(
                    device_id=1000,
                    object_type="analogOutput",
                    instance=1,
                    request=BACnetPointWriteRequest(value=22.5),
                )
            assert exc_info.value.status_code == 502

    @pytest.mark.asyncio
    async def test_write_point_timeout(self, mock_bacnet_client):
        from app.api.niagara_bacnet import write_point
        from app.models.niagara import BACnetPointWriteRequest
        from fastapi import HTTPException

        mock_bacnet_client.write_point = AsyncMock(
            side_effect=BACnetTimeoutError("Timed out")
        )

        with patch("app.api.niagara_bacnet.get_bacnet_client", return_value=mock_bacnet_client):
            with pytest.raises(HTTPException) as exc_info:
                await write_point(
                    device_id=1000,
                    object_type="analogOutput",
                    instance=1,
                    request=BACnetPointWriteRequest(value=22.5),
                )
            assert exc_info.value.status_code == 504


# ---------------------------------------------------------------------------
# COV Subscriptions
# ---------------------------------------------------------------------------

class TestCOVSubscriptionEndpoints:
    """Tests for COV subscription endpoint functions."""

    @pytest.mark.asyncio
    async def test_create_subscription(self, mock_bacnet_client):
        from app.api.niagara_bacnet import create_cov_subscription
        from app.models.niagara import BACnetCOVSubscribeRequest, BACnetCOVPoint

        mock_sub = COVSubscription(
            subscription_id="test-sub-123",
            device_id=1000,
            points=[("analogInput", 0), ("analogInput", 1)],
            callback=lambda x, y: None,
            lifetime=60,
        )
        mock_bacnet_client.subscribe_to_points = AsyncMock(return_value=mock_sub)

        with patch("app.api.niagara_bacnet.get_bacnet_client", return_value=mock_bacnet_client):
            result = await create_cov_subscription(
                BACnetCOVSubscribeRequest(
                    device_id=1000,
                    points=[
                        BACnetCOVPoint(object_type="analogInput", instance=0),
                        BACnetCOVPoint(object_type="analogInput", instance=1),
                    ],
                    lifetime=60,
                )
            )

        assert result.subscription_id == "test-sub-123"
        assert result.device_id == 1000
        assert len(result.points) == 2
        assert result.active is True

    @pytest.mark.asyncio
    async def test_list_subscriptions_empty(self, mock_bacnet_client):
        from app.api.niagara_bacnet import list_cov_subscriptions

        with patch("app.api.niagara_bacnet.get_bacnet_client", return_value=mock_bacnet_client):
            result = await list_cov_subscriptions()

        assert result.count == 0
        assert result.subscriptions == []

    @pytest.mark.asyncio
    async def test_list_subscriptions_with_active(self, mock_bacnet_client):
        from app.api.niagara_bacnet import list_cov_subscriptions

        mock_sub = COVSubscription(
            subscription_id="active-sub",
            device_id=1000,
            points=[("analogInput", 0)],
            callback=lambda x, y: None,
            lifetime=60,
        )
        mock_bacnet_client.list_subscriptions.return_value = [mock_sub]

        with patch("app.api.niagara_bacnet.get_bacnet_client", return_value=mock_bacnet_client):
            result = await list_cov_subscriptions()

        assert result.count == 1
        assert result.subscriptions[0].subscription_id == "active-sub"

    @pytest.mark.asyncio
    async def test_cancel_subscription(self, mock_bacnet_client):
        from app.api.niagara_bacnet import cancel_cov_subscription

        mock_bacnet_client.cancel_subscription = AsyncMock(return_value=True)

        with patch("app.api.niagara_bacnet.get_bacnet_client", return_value=mock_bacnet_client):
            result = await cancel_cov_subscription("test-sub-123")

        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_cancel_subscription_not_found(self, mock_bacnet_client):
        from app.api.niagara_bacnet import cancel_cov_subscription
        from fastapi import HTTPException

        mock_bacnet_client.cancel_subscription = AsyncMock(return_value=False)

        with patch("app.api.niagara_bacnet.get_bacnet_client", return_value=mock_bacnet_client):
            with pytest.raises(HTTPException) as exc_info:
                await cancel_cov_subscription("nonexistent")
            assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# Pydantic model validation
# ---------------------------------------------------------------------------

class TestModelValidation:
    """Tests for BACnet Pydantic model validation."""

    def test_discover_request_defaults(self):
        from app.models.niagara import BACnetDiscoverRequest

        req = BACnetDiscoverRequest()
        assert req.timeout == 5.0

    def test_discover_request_custom(self):
        from app.models.niagara import BACnetDiscoverRequest

        req = BACnetDiscoverRequest(timeout=10.0)
        assert req.timeout == 10.0

    def test_write_request_valid_priority(self):
        from app.models.niagara import BACnetPointWriteRequest

        req = BACnetPointWriteRequest(value=42, priority=1)
        assert req.priority == 1

        req = BACnetPointWriteRequest(value=42, priority=16)
        assert req.priority == 16

    def test_write_request_invalid_priority_low(self):
        from app.models.niagara import BACnetPointWriteRequest

        with pytest.raises(Exception):
            BACnetPointWriteRequest(value=42, priority=0)

    def test_write_request_invalid_priority_high(self):
        from app.models.niagara import BACnetPointWriteRequest

        with pytest.raises(Exception):
            BACnetPointWriteRequest(value=42, priority=17)

    def test_write_request_default_priority(self):
        from app.models.niagara import BACnetPointWriteRequest

        req = BACnetPointWriteRequest(value=42)
        assert req.priority == 8

    def test_cov_subscribe_request(self):
        from app.models.niagara import BACnetCOVSubscribeRequest, BACnetCOVPoint

        req = BACnetCOVSubscribeRequest(
            device_id=1000,
            points=[BACnetCOVPoint(object_type="analogInput", instance=0)],
            lifetime=120,
        )
        assert req.device_id == 1000
        assert len(req.points) == 1
        assert req.lifetime == 120

    def test_device_info_model(self):
        from app.models.niagara import BACnetDeviceInfo

        device = BACnetDeviceInfo(
            device_id=1000,
            ip_address="192.168.1.100",
            vendor_name="Tridium",
            model_name="JACE-8000",
        )
        assert device.device_id == 1000
        assert device.vendor_name == "Tridium"
        assert device.model_name == "JACE-8000"

    def test_point_info_model(self):
        from app.models.niagara import BACnetPointInfo

        point = BACnetPointInfo(
            object_type="analogInput",
            instance=0,
            name="Zone Temp",
            units="degF",
            present_value=72.5,
            writable=False,
        )
        assert point.object_type == "analogInput"
        assert point.present_value == 72.5
        assert point.writable is False

    def test_client_status_model(self):
        from app.models.niagara import BACnetClientStatus

        status = BACnetClientStatus(
            started=True,
            port=47808,
            active_subscriptions=3,
            cached_devices=2,
        )
        assert status.started is True
        assert status.port == 47808
        assert status.active_subscriptions == 3
