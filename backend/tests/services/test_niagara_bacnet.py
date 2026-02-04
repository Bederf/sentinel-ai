"""Tests for Niagara BACnet/IP client service.

Tests cover:
- Client lifecycle (start/stop)
- Device discovery
- Point read/write operations
- COV subscriptions
- Retry logic and error handling
- Point cache management
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.niagara.bacnet_client import (
    NiagaraBACnetClient,
    BACnetException,
    BACnetTimeoutError,
    BACnetReadError,
    BACnetWriteError,
    BACnetDeviceNotFoundError,
    BACnetObjectType,
    COVSubscription,
    DiscoveredDevice,
    DiscoveredPoint,
    get_bacnet_client,
)

import app.services.niagara.bacnet_client as bacnet_module


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    """Create a fresh BACnet client instance."""
    return NiagaraBACnetClient(ip="127.0.0.1", port=47808)


@pytest.fixture
def mock_bac0():
    """Create a mock BAC0 lite instance."""
    mock = MagicMock()
    mock.whois.return_value = [
        ("192.168.1.100", 1234),
        ("192.168.1.101", 5678),
    ]
    mock.read.return_value = 22.5
    mock.write.return_value = None
    mock.disconnect.return_value = None
    return mock


@pytest.fixture
async def started_client(client, mock_bac0):
    """Create a BACnet client with mocked BAC0 backend."""
    # Mock the module-level _BAC0 variable
    mock_bac0_module = MagicMock()
    mock_bac0_module.lite.return_value = mock_bac0

    original_bac0 = bacnet_module._BAC0
    bacnet_module._BAC0 = mock_bac0_module

    try:
        await client.start()
        # Ensure the mock backend is set
        client._bacnet = mock_bac0
        yield client
    finally:
        await client.stop()
        bacnet_module._BAC0 = original_bac0


# ---------------------------------------------------------------------------
# Lifecycle tests
# ---------------------------------------------------------------------------

class TestClientLifecycle:
    """Tests for client start/stop operations."""

    @pytest.mark.asyncio
    async def test_client_not_started_by_default(self, client):
        """Client should not be started on creation."""
        assert not client.is_running
        assert client._bacnet is None

    @pytest.mark.asyncio
    async def test_start_initializes_bac0(self):
        """Starting client should initialize BAC0.lite()."""
        client = NiagaraBACnetClient(ip="127.0.0.1")
        mock_bac0_mod = MagicMock()
        mock_instance = MagicMock()
        mock_bac0_mod.lite.return_value = mock_instance

        original = bacnet_module._BAC0
        bacnet_module._BAC0 = mock_bac0_mod
        try:
            await client.start()
            mock_bac0_mod.lite.assert_called_once()
            assert client.is_running
            assert client._bacnet == mock_instance
            await client.stop()
        finally:
            bacnet_module._BAC0 = original

    @pytest.mark.asyncio
    async def test_stop_disconnects(self):
        """Stopping client should disconnect BAC0."""
        client = NiagaraBACnetClient()
        mock_bacnet = MagicMock()
        client._bacnet = mock_bacnet
        client._started = True

        await client.stop()

        mock_bacnet.disconnect.assert_called_once()
        assert not client.is_running

    @pytest.mark.asyncio
    async def test_ensure_started_raises_when_not_started(self, client):
        """Operations should raise when client not started."""
        with pytest.raises(BACnetException, match="not started"):
            client._ensure_started()

    @pytest.mark.asyncio
    async def test_start_raises_when_bac0_not_installed(self):
        """Start should raise when BAC0 is not installed."""
        client = NiagaraBACnetClient()
        original = bacnet_module._BAC0
        bacnet_module._BAC0 = None
        try:
            with pytest.raises(BACnetException, match="not installed"):
                await client.start()
        finally:
            bacnet_module._BAC0 = original

    @pytest.mark.asyncio
    async def test_double_start_is_safe(self):
        """Starting an already-started client should be a no-op."""
        client = NiagaraBACnetClient()
        mock_mod = MagicMock()
        mock_mod.lite.return_value = MagicMock()

        original = bacnet_module._BAC0
        bacnet_module._BAC0 = mock_mod
        try:
            await client.start()
            await client.start()  # Should not raise
            mock_mod.lite.assert_called_once()  # Only called once
            await client.stop()
        finally:
            bacnet_module._BAC0 = original


# ---------------------------------------------------------------------------
# Device discovery tests
# ---------------------------------------------------------------------------

class TestDeviceDiscovery:
    """Tests for BACnet device discovery."""

    @pytest.mark.asyncio
    async def test_discover_devices_returns_list(self, started_client, mock_bac0):
        """Discovery should return DiscoveredDevice objects."""
        devices = await started_client.discover_devices(timeout=2)

        assert len(devices) == 2
        assert isinstance(devices[0], DiscoveredDevice)
        assert devices[0].device_id == 1234
        assert devices[0].ip_address == "192.168.1.100"
        assert devices[1].device_id == 5678

    @pytest.mark.asyncio
    async def test_discover_empty_network(self, started_client, mock_bac0):
        """Discovery on empty network should return empty list."""
        mock_bac0.whois.return_value = []
        devices = await started_client.discover_devices()
        assert devices == []

    @pytest.mark.asyncio
    async def test_discover_handles_none_response(self, started_client, mock_bac0):
        """Discovery should handle None response gracefully."""
        mock_bac0.whois.return_value = None
        devices = await started_client.discover_devices()
        assert devices == []

    @pytest.mark.asyncio
    async def test_discovered_device_to_dict(self):
        """DiscoveredDevice should serialize to dict."""
        device = DiscoveredDevice(
            device_id=1234,
            ip_address="192.168.1.100",
            vendor_name="Tridium",
            model_name="JACE 8000",
        )
        d = device.to_dict()
        assert d["device_id"] == 1234
        assert d["vendor_name"] == "Tridium"
        assert d["model_name"] == "JACE 8000"


# ---------------------------------------------------------------------------
# Point read tests
# ---------------------------------------------------------------------------

class TestPointRead:
    """Tests for point read operations."""

    @pytest.mark.asyncio
    async def test_read_point_returns_value(self, started_client, mock_bac0):
        """Read should return point value."""
        mock_bac0.read.return_value = 22.5

        value = await started_client.read_point(1234, "analogValue", 0)
        assert value == 22.5

    @pytest.mark.asyncio
    async def test_read_multiple_points(self, started_client, mock_bac0):
        """Should read multiple points and return dict."""
        mock_bac0.read.side_effect = [22.5, True, 3]

        results = await started_client.read_multiple_points(
            1234,
            [("analogValue", 0), ("binaryValue", 1), ("multiStateValue", 2)],
        )

        assert results["analogValue:0"] == 22.5
        assert results["binaryValue:1"] is True
        assert results["multiStateValue:2"] == 3

    @pytest.mark.asyncio
    async def test_read_handles_partial_failure(self, started_client, mock_bac0):
        """Reading multiple points should handle individual failures."""
        mock_bac0.read.side_effect = [22.5, Exception("timeout"), 3]

        results = await started_client.read_multiple_points(
            1234,
            [("analogValue", 0), ("binaryValue", 1), ("multiStateValue", 2)],
        )

        assert results["analogValue:0"] == 22.5
        assert results["binaryValue:1"] is None  # Failed read
        assert results["multiStateValue:2"] == 3


# ---------------------------------------------------------------------------
# Point write tests
# ---------------------------------------------------------------------------

class TestPointWrite:
    """Tests for point write operations."""

    @pytest.mark.asyncio
    async def test_write_point_succeeds(self, started_client, mock_bac0):
        """Write should call BAC0 write with correct format."""
        result = await started_client.write_point(
            1234, "analogValue", 0, 22.5, priority=8
        )
        assert result is True
        mock_bac0.write.assert_called()

    @pytest.mark.asyncio
    async def test_write_invalid_priority_raises(self, started_client):
        """Write with invalid priority should raise ValueError."""
        with pytest.raises(ValueError, match="priority must be 1-16"):
            await started_client.write_point(1234, "analogValue", 0, 22.5, priority=17)

    @pytest.mark.asyncio
    async def test_write_zero_priority_raises(self, started_client):
        """Write with zero priority should raise ValueError."""
        with pytest.raises(ValueError, match="priority must be 1-16"):
            await started_client.write_point(1234, "analogValue", 0, 22.5, priority=0)


# ---------------------------------------------------------------------------
# Point list / cache tests
# ---------------------------------------------------------------------------

class TestPointListDiscovery:
    """Tests for point list discovery and caching."""

    @pytest.mark.asyncio
    async def test_read_point_list(self, started_client, mock_bac0):
        """Should enumerate points from device objectList."""
        mock_bac0.read.return_value = [
            ("analogValue", 0),
            ("analogValue", 1),
            ("binaryInput", 0),
        ]

        points = await started_client.read_point_list(1234)

        assert len(points) == 3
        assert isinstance(points[0], DiscoveredPoint)
        assert points[0].object_type == "analogValue"
        assert points[0].instance == 0

    @pytest.mark.asyncio
    async def test_point_list_caching(self, started_client, mock_bac0):
        """Point list should be cached after first read."""
        mock_bac0.read.return_value = [("analogValue", 0)]

        points1 = await started_client.read_point_list(1234)
        points2 = await started_client.read_point_list(1234, use_cache=True)

        assert points1 == points2

    @pytest.mark.asyncio
    async def test_clear_point_cache(self, started_client, mock_bac0):
        """Cache clear should force re-read."""
        mock_bac0.read.return_value = [("analogValue", 0)]
        await started_client.read_point_list(1234)

        started_client.clear_point_cache(1234)
        assert 1234 not in started_client._point_cache

    @pytest.mark.asyncio
    async def test_filter_by_object_type(self, started_client, mock_bac0):
        """Point list should support object type filtering."""
        mock_bac0.read.return_value = [
            ("analogValue", 0),
            ("binaryInput", 0),
            ("analogValue", 1),
        ]

        points = await started_client.read_point_list(
            1234, object_types=["analogValue"]
        )
        assert len(points) == 2
        assert all(p.object_type == "analogValue" for p in points)


# ---------------------------------------------------------------------------
# COV subscription tests
# ---------------------------------------------------------------------------

class TestCOVSubscriptions:
    """Tests for Change-of-Value subscriptions."""

    @pytest.mark.asyncio
    async def test_create_subscription(self, started_client, mock_bac0):
        """Should create a COV subscription."""
        callback = MagicMock()

        sub = await started_client.subscribe_to_points(
            device_id=1234,
            points=[("analogValue", 0)],
            callback=callback,
            lifetime=60,
        )

        assert isinstance(sub, COVSubscription)
        assert sub.active
        assert sub.device_id == 1234
        assert len(sub.points) == 1

        # Cleanup
        await started_client.cancel_subscription(sub.subscription_id)

    @pytest.mark.asyncio
    async def test_cancel_subscription(self, started_client, mock_bac0):
        """Should cancel and remove subscription."""
        callback = MagicMock()
        sub = await started_client.subscribe_to_points(
            device_id=1234,
            points=[("analogValue", 0)],
            callback=callback,
        )

        result = await started_client.cancel_subscription(sub.subscription_id)
        assert result is True
        assert not sub.active
        assert sub.subscription_id not in started_client._subscriptions

    @pytest.mark.asyncio
    async def test_cancel_nonexistent_subscription(self, started_client):
        """Cancelling unknown subscription should return False."""
        result = await started_client.cancel_subscription("nonexistent-id")
        assert result is False

    @pytest.mark.asyncio
    async def test_list_subscriptions(self, started_client, mock_bac0):
        """Should list active subscriptions."""
        cb = MagicMock()
        sub1 = await started_client.subscribe_to_points(
            1234, [("analogValue", 0)], cb
        )
        sub2 = await started_client.subscribe_to_points(
            1234, [("binaryValue", 1)], cb
        )

        active = started_client.list_subscriptions()
        assert len(active) == 2

        await started_client.cancel_subscription(sub1.subscription_id)
        active = started_client.list_subscriptions()
        assert len(active) == 1

        # Cleanup
        await started_client.cancel_subscription(sub2.subscription_id)

    def test_cov_subscription_expiry(self):
        """COV subscription should track expiry correctly."""
        sub = COVSubscription(
            subscription_id="test-1",
            device_id=1234,
            points=[("analogValue", 0)],
            callback=lambda p, v: None,
            lifetime=0,  # Immediately expired
        )
        assert sub.is_expired

    def test_cov_subscription_renewal(self):
        """COV subscription renewal should extend expiry."""
        sub = COVSubscription(
            subscription_id="test-1",
            device_id=1234,
            points=[("analogValue", 0)],
            callback=lambda p, v: None,
            lifetime=60,
        )
        old_expiry = sub.expires_at
        sub.renew()
        assert sub.expires_at > old_expiry

    def test_cov_subscription_to_dict(self):
        """COV subscription should serialize to dict."""
        sub = COVSubscription(
            subscription_id="test-1",
            device_id=1234,
            points=[("analogValue", 0)],
            callback=lambda p, v: None,
            lifetime=60,
        )
        d = sub.to_dict()
        assert d["subscription_id"] == "test-1"
        assert d["device_id"] == 1234
        assert d["active"] is True


# ---------------------------------------------------------------------------
# Retry logic tests
# ---------------------------------------------------------------------------

class TestRetryLogic:
    """Tests for retry and error handling."""

    @pytest.mark.asyncio
    async def test_retry_succeeds_on_second_attempt(self, started_client):
        """Should succeed after transient failure."""
        call_count = 0

        async def flaky_operation(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ConnectionError("transient error")
            return "success"

        result = await started_client._retry_operation(flaky_operation)
        assert result == "success"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_retry_exhausted_raises(self, started_client):
        """Should raise after all retries exhausted."""

        async def always_fails(*args, **kwargs):
            raise ConnectionError("persistent error")

        with pytest.raises(BACnetException, match="failed after 3 attempts"):
            await started_client._retry_operation(always_fails, max_retries=3)

    @pytest.mark.asyncio
    async def test_timeout_raises_bacnet_timeout(self, started_client):
        """Timeout errors should raise BACnetTimeoutError."""

        async def timeout_op(*args, **kwargs):
            raise asyncio.TimeoutError()

        with pytest.raises(BACnetTimeoutError):
            await started_client._retry_operation(timeout_op, max_retries=1)


# ---------------------------------------------------------------------------
# Utility tests
# ---------------------------------------------------------------------------

class TestUtility:
    """Tests for utility methods."""

    def test_get_status(self, client):
        """Should return client status dict."""
        status = client.get_status()
        assert status["started"] is False
        assert status["port"] == 47808
        assert status["active_subscriptions"] == 0

    def test_bacnet_object_type_enum(self):
        """BACnetObjectType enum should have expected values."""
        assert BACnetObjectType.ANALOG_INPUT == "analogInput"
        assert BACnetObjectType.BINARY_OUTPUT == "binaryOutput"
        assert BACnetObjectType.DEVICE == "device"

    def test_discovered_point_writable_flag(self):
        """Output and value types should be writable."""
        writable_point = DiscoveredPoint(
            object_type="analogOutput", instance=0, writable=True
        )
        assert writable_point.writable

        readonly_point = DiscoveredPoint(
            object_type="analogInput", instance=0, writable=False
        )
        assert not readonly_point.writable


# ---------------------------------------------------------------------------
# Singleton factory tests
# ---------------------------------------------------------------------------

class TestSingletonFactory:
    """Tests for the singleton factory function."""

    def test_get_bacnet_client_returns_instance(self):
        """Factory should return a NiagaraBACnetClient."""
        bacnet_module._client_instance = None
        client = get_bacnet_client()
        assert isinstance(client, NiagaraBACnetClient)
        bacnet_module._client_instance = None

    def test_get_bacnet_client_returns_same_instance(self):
        """Factory should return the same instance on subsequent calls."""
        bacnet_module._client_instance = None
        client1 = get_bacnet_client()
        client2 = get_bacnet_client()
        assert client1 is client2
        bacnet_module._client_instance = None
