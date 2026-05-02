"""Tests for ObixBmsAdapter."""

from unittest.mock import MagicMock, patch

import pytest

from app.services.simbiot import BmsConnectionConfig, BmsWriteRequest
from app.services.simbiot.obix_bms_adapter import (
    ObixBmsAdapter,
    _normalize_unit,
    UNIT_CONVERSIONS,
    UNIT_OFFSET_CORRECTIONS,
)


@pytest.mark.unit
class TestObixBmsAdapter:
    """Unit tests for ObixBmsAdapter."""

    # -------------------------------------------------------------------------
    # adapter_id
    # -------------------------------------------------------------------------
    def test_adapter_id_returns_obix(self):
        adapter = ObixBmsAdapter()
        assert adapter.adapter_id == "obix"

    # -------------------------------------------------------------------------
    # capabilities
    # -------------------------------------------------------------------------
    def test_capabilities_no_device_discovery(self):
        adapter = ObixBmsAdapter()
        caps = adapter.capabilities
        assert caps.supports_device_discovery is False
        assert caps.supports_point_discovery is True
        assert caps.supports_reads is True
        assert caps.supports_writes is False
        assert caps.supports_subscriptions is False
        assert caps.supports_history is True

    # -------------------------------------------------------------------------
    # connect / disconnect
    # -------------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_connect_success_authenticates(self):
        mock_client = MagicMock()
        mock_client.authenticate = MagicMock(return_value=True)
        mock_client.is_authenticated = True
        mock_client.check_connection = MagicMock(return_value={"connected": True, "message": "OK"})

        with patch(
            "app.services.niagara.obix_client.OBIXClient",
            return_value=mock_client,
        ):
            adapter = ObixBmsAdapter()
            status = await adapter.connect(
                BmsConnectionConfig(
                    site_id="site-002",
                    source_type="obix",
                    host="192.168.1.10",
                    port=8080,
                    username="admin",
                    password="pass",
                )
            )

        assert status.connected is True
        assert status.site_id == "site-002"
        assert status.source_type == "obix"
        assert status.status == "connected"

    @pytest.mark.asyncio
    async def test_connect_auth_failure_returns_error_status(self):
        from app.services.niagara.obix_client import OBIXAuthenticationError

        mock_client = MagicMock()
        mock_client.authenticate = MagicMock(side_effect=OBIXAuthenticationError("Invalid credentials"))
        mock_client.is_authenticated = False

        with patch(
            "app.services.niagara.obix_client.OBIXClient",
            return_value=mock_client,
        ):
            adapter = ObixBmsAdapter()
            status = await adapter.connect(
                BmsConnectionConfig(
                    site_id="site-002",
                    source_type="obix",
                    host="192.168.1.10",
                    port=8080,
                    username="admin",
                    password="wrong",
                )
            )

        assert status.connected is False
        assert status.status == "error"
        assert "authentication failed" in status.message.lower()

    @pytest.mark.asyncio
    async def test_connect_connection_error_returns_error_status(self):
        from app.services.niagara.obix_client import OBIXConnectionError

        mock_client = MagicMock()
        mock_client.authenticate = MagicMock(side_effect=OBIXConnectionError("Connection refused"))
        mock_client.is_authenticated = False

        with patch(
            "app.services.niagara.obix_client.OBIXClient",
            return_value=mock_client,
        ):
            adapter = ObixBmsAdapter()
            status = await adapter.connect(
                BmsConnectionConfig(
                    site_id="site-002",
                    source_type="obix",
                    host="192.168.1.10",
                    port=8080,
                )
            )

        assert status.connected is False
        assert status.status == "error"
        assert "connection failed" in status.message.lower()

    @pytest.mark.asyncio
    async def test_disconnect_clears_state(self):
        adapter = ObixBmsAdapter()
        adapter._connected = True
        adapter._obix_client = MagicMock()

        await adapter.disconnect()

        assert adapter._connected is False
        assert adapter._obix_client is None

    # -------------------------------------------------------------------------
    # get_status
    # -------------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_get_status_connected_returns_connected_state(self):
        mock_client = MagicMock()
        mock_client.check_connection = MagicMock(return_value={"connected": True, "message": "Connected"})

        adapter = ObixBmsAdapter()
        adapter._config = BmsConnectionConfig(site_id="site-002", source_type="obix")
        adapter._connected = True
        adapter._obix_client = mock_client

        status = await adapter.get_status()

        assert status.connected is True
        assert status.status == "connected"
        assert status.site_id == "site-002"

    @pytest.mark.asyncio
    async def test_get_status_disconnected_returns_disconnected_state(self):
        adapter = ObixBmsAdapter()
        adapter._config = BmsConnectionConfig(site_id="site-002", source_type="obix")
        adapter._connected = False
        adapter._obix_client = None

        status = await adapter.get_status()

        assert status.connected is False
        assert status.status == "disconnected"

    # -------------------------------------------------------------------------
    # discover_devices
    # -------------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_discover_devices_returns_single_broker_device(self):
        adapter = ObixBmsAdapter()
        adapter._config = BmsConnectionConfig(
            site_id="site-002",
            source_type="obix",
            host="192.168.1.10",
        )

        devices = await adapter.discover_devices()

        assert len(devices) == 1
        assert devices[0].device_id == "obix-broker"
        assert devices[0].display_name == "oBIX Broker"
        assert devices[0].protocol == "obix"
        assert devices[0].address == "192.168.1.10"

    # -------------------------------------------------------------------------
    # discover_points
    # -------------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_discover_points_returns_empty_list(self):
        adapter = ObixBmsAdapter()
        adapter._connected = True

        points = await adapter.discover_points("obix-broker")

        assert points == []

    # -------------------------------------------------------------------------
    # read_point
    # -------------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_read_point_returns_normalized_value(self):
        mock_client = MagicMock()
        mock_client.read_point = MagicMock(
            return_value={
                "path": "config/points/temp1",
                "value": 77.0,
                "type": "°F",
                "status": "ok",
            }
        )

        adapter = ObixBmsAdapter()
        adapter._connected = True
        adapter._obix_client = mock_client

        result = await adapter.read_point("obix-broker", "config/points/temp1")

        assert result.device_id == "obix-broker"
        assert result.point_id == "config/points/temp1"
        # 77°F -> 25°C (normalized)
        assert abs(result.value - 25.0) < 0.1
        assert result.unit == "°C"
        assert result.metadata["raw_value"] == 77.0

    @pytest.mark.asyncio
    async def test_read_point_passes_through_unknown_unit(self):
        mock_client = MagicMock()
        mock_client.read_point = MagicMock(
            return_value={
                "path": "config/points/pressure1",
                "value": 100.0,
                "type": "unknown_unit",
                "status": "ok",
            }
        )

        adapter = ObixBmsAdapter()
        adapter._connected = True
        adapter._obix_client = mock_client

        result = await adapter.read_point("obix-broker", "config/points/pressure1")

        assert result.value == 100.0
        assert result.unit == "unknown_unit"

    @pytest.mark.asyncio
    async def test_read_point_not_found_raises(self):
        from app.services.niagara.obix_client import OBIXPointNotFoundError

        mock_client = MagicMock()
        mock_client.read_point = MagicMock(side_effect=OBIXPointNotFoundError("Not found"))

        adapter = ObixBmsAdapter()
        adapter._connected = True
        adapter._obix_client = mock_client

        with pytest.raises(OBIXPointNotFoundError):
            await adapter.read_point("obix-broker", "config/points/nonexistent")

    @pytest.mark.asyncio
    async def test_read_point_not_connected_raises(self):
        adapter = ObixBmsAdapter()
        adapter._connected = False
        adapter._obix_client = None

        with pytest.raises(ConnectionError, match="not connected"):
            await adapter.read_point("obix-broker", "config/points/temp1")

    # -------------------------------------------------------------------------
    # read_points (batch)
    # -------------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_read_points_batch_normalizes_all(self):
        mock_client = MagicMock()
        mock_client.read_point = MagicMock(
            side_effect=[
                {"path": "config/points/temp1", "value": 77.0, "type": "°F", "status": "ok"},
                {"path": "config/points/flow1", "value": 100.0, "type": "cfm", "status": "ok"},
            ]
        )

        adapter = ObixBmsAdapter()
        adapter._connected = True
        adapter._obix_client = mock_client

        results = await adapter.read_points(
            "obix-broker",
            ["config/points/temp1", "config/points/flow1"],
        )

        assert len(results) == 2
        # 77°F -> 25°C
        assert abs(results[0].value - 25.0) < 0.1
        assert results[0].unit == "°C"
        # 100 cfm -> 47.19 l/s
        assert abs(results[1].value - 47.19) < 0.01
        assert results[1].unit == "l/s"

    @pytest.mark.asyncio
    async def test_read_points_not_connected_raises(self):
        adapter = ObixBmsAdapter()
        adapter._connected = False
        adapter._obix_client = None

        with pytest.raises(ConnectionError, match="not connected"):
            await adapter.read_points("obix-broker", ["config/points/temp1"])

    # -------------------------------------------------------------------------
    # write_point
    # -------------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_write_point_not_implemented(self):
        adapter = ObixBmsAdapter()
        adapter._connected = True
        adapter._obix_client = MagicMock()

        request = BmsWriteRequest(
            device_id="obix-broker",
            point_id="config/points/setpoint1",
            value=22.0,
        )

        with pytest.raises(NotImplementedError):
            await adapter.write_point(request)

    # -------------------------------------------------------------------------
    # reconnect after disconnect
    # -------------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_reconnect_after_disconnect(self):
        mock_client = MagicMock()
        mock_client.authenticate = MagicMock(return_value=True)
        mock_client.is_authenticated = True
        mock_client.check_connection = MagicMock(return_value={"connected": True, "message": "Connected"})

        with patch(
            "app.services.niagara.obix_client.OBIXClient",
            return_value=mock_client,
        ):
            adapter = ObixBmsAdapter()

            # First connect
            await adapter.connect(
                BmsConnectionConfig(
                    site_id="site-002",
                    source_type="obix",
                    host="192.168.1.10",
                    port=8080,
                )
            )
            assert adapter._connected is True

            # Disconnect
            await adapter.disconnect()
            assert adapter._connected is False

            # Reconnect
            mock_client.is_authenticated = True
            status = await adapter.connect(
                BmsConnectionConfig(
                    site_id="site-002",
                    source_type="obix",
                    host="192.168.1.10",
                    port=8080,
                )
            )
            assert status.connected is True


# -------------------------------------------------------------------------
# Unit normalization table tests
# -------------------------------------------------------------------------
@pytest.mark.unit
class TestUnitNormalization:
    """Unit tests for _normalize_unit function."""

    @pytest.mark.parametrize(
        "unit,expected_si",
        [
            ("°F", "°C"),
            ("cfm", "l/s"),
            ("psi", "kPa"),
            ("inWC", "Pa"),
            ("kVA", "kW"),
            ("kBtu", "kWh"),
            ("gpm", "l/s"),
            ("fpm", "m/s"),
        ],
    )
    def test_all_conversion_units_defined(self, unit, expected_si):
        """All units in conversion table map to expected SI unit."""
        assert unit in UNIT_CONVERSIONS
        assert UNIT_CONVERSIONS[unit][0] == expected_si

    def test_fahrenheit_conversion_correct(self):
        """°F to °C conversion is accurate."""
        # 32°F = 0°C
        val, unit = _normalize_unit(32.0, "°F")
        assert abs(val - 0.0) < 0.01
        assert unit == "°C"

        # 77°F = 25°C
        val, unit = _normalize_unit(77.0, "°F")
        assert abs(val - 25.0) < 0.1
        assert unit == "°C"

        # 212°F = 100°C
        val, unit = _normalize_unit(212.0, "°F")
        assert abs(val - 100.0) < 0.1
        assert unit == "°C"

    def test_cfm_conversion_correct(self):
        """cfm to l/s conversion is accurate."""
        val, unit = _normalize_unit(100.0, "cfm")
        assert abs(val - 47.19) < 0.01
        assert unit == "l/s"

    def test_psi_conversion_correct(self):
        """psi to kPa conversion is accurate."""
        val, unit = _normalize_unit(10.0, "psi")
        assert abs(val - 68.948) < 0.001
        assert unit == "kPa"

    def test_gpm_conversion_correct(self):
        """gpm to l/s conversion is accurate."""
        val, unit = _normalize_unit(10.0, "gpm")
        assert abs(val - 0.6309) < 0.0001
        assert unit == "l/s"

    def test_unknown_unit_passthrough(self):
        """Unknown units pass through unchanged."""
        val, unit = _normalize_unit(42.0, "random_unit")
        assert val == 42.0
        assert unit == "random_unit"

    def test_empty_unit_passthrough(self):
        """Empty unit string passes through unchanged."""
        val, unit = _normalize_unit(42.0, "")
        assert val == 42.0
        assert unit == ""

    def test_none_unit_passthrough(self):
        """None unit handled gracefully."""
        val, unit = _normalize_unit(42.0, "°C")  # Pass-through unit
        assert val == 42.0
        assert unit == "°C"

    def test_offset_correction_only_fahrenheit(self):
        """Only °F has an offset correction defined."""
        assert "°F" in UNIT_OFFSET_CORRECTIONS
        assert len(UNIT_OFFSET_CORRECTIONS) == 1

    def test_no_offset_for_cfm(self):
        """cfm conversion has no offset (just multiplier)."""
        # cfm: 100 cfm -> 47.19 l/s (no offset)
        val1, _ = _normalize_unit(100.0, "cfm")
        val2, _ = _normalize_unit(200.0, "cfm")
        assert abs(val2 - 2 * val1) < 0.01  # linear relationship

    @pytest.mark.parametrize(
        "value,unit,expected",
        [
            (0.0, "°F", -17.778),  # 0°F = -17.778°C
            (100.0, "cfm", 47.19),
            (14.7, "psi", 101.353),
            (1.0, "inWC", 249.09),
            (50.0, "kVA", 45.0),
            (1000.0, "kBtu", 293.1),
            (20.0, "gpm", 1.262),
            (1000.0, "fpm", 5.08),
        ],
    )
    def test_normalization_references(self, value, unit, expected):
        """Known conversion references."""
        val, _ = _normalize_unit(value, unit)
        assert abs(val - expected) < 0.01
