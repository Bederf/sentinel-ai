"""Tests for RealHuaweiConnector — Modbus TCP reads from Huawei SUN2000/LUNA2000.

All tests mock pymodbus to avoid real hardware dependency.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.solar import DataSource
from app.services.solar_connector_huawei import (
    RealHuaweiConnector,
    HUAWEI_SUN2000_REGISTERS,
    HUAWEI_LUNA2000_REGISTERS,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def inverter_configs():
    return [
        {
            "id": "S002-INV-H01",
            "plant_id": "plant-roof-01",
            "site_id": "site-002",
            "name": "Inverter 1",
            "model": "SUN2000-100KTL-M2",
            "rated_kva": 100,
            "mppt_count": 10,
            "ip": "10.1.1.101",
            "port": 502,
            "unit_id": 1,
        }
    ]


@pytest.fixture
def bess_config():
    return {
        "container_id": "S002-BESS-01",
        "site_id": "site-002",
        "name": "LUNA2000 BESS",
        "model": "LUNA2000-200KWH-2H1",
        "capacity_kwh": 200,
        "rated_power_kw": 100,
        "rack_count": 2,
    }


@pytest.fixture
def connector(inverter_configs, bess_config):
    return RealHuaweiConnector(
        inverters=inverter_configs,
        bess=bess_config,
    )


def _make_mock_client(registers=None, error=False):
    """Create a mock AsyncModbusTcpClient that returns specified register values."""
    client = AsyncMock()
    client.connect = AsyncMock(return_value=True)
    client.close = MagicMock()

    result = MagicMock()
    if error:
        result.isError.return_value = True
    else:
        result.isError.return_value = False
        result.registers = registers or [0]

    client.read_holding_registers = AsyncMock(return_value=result)
    return client


# ---------------------------------------------------------------------------
# Connection tests
# ---------------------------------------------------------------------------


class TestConnect:
    """Test Modbus TCP connection."""

    @pytest.mark.asyncio
    async def test_connect_success(self, connector):
        mock_client = _make_mock_client()

        with patch("app.config.settings.settings") as mock_settings:
            mock_settings.modbus_bess_ip = "10.1.1.100"
            mock_settings.modbus_bess_port = 502
            mock_settings.modbus_bess_timeout_s = 5

            with (
                patch(
                    "app.services.solar_connector_huawei.AsyncModbusTcpClient",
                    return_value=mock_client,
                )
                if False
                else patch(
                    "pymodbus.client.AsyncModbusTcpClient",
                    return_value=mock_client,
                )
            ):
                result = await connector.connect()
                assert result is True
                assert connector.is_connected()

    @pytest.mark.asyncio
    async def test_connect_no_ip_configured(self, connector):
        with patch("app.config.settings.settings") as mock_settings:
            mock_settings.modbus_bess_ip = ""
            mock_settings.modbus_bess_port = 502
            mock_settings.modbus_bess_timeout_s = 5

            result = await connector.connect()
            assert result is False
            assert not connector.is_connected()

    @pytest.mark.asyncio
    async def test_disconnect(self, connector):
        connector._client = _make_mock_client()
        connector._status.connected = True

        await connector.disconnect()
        assert not connector.is_connected()
        assert connector._client is None


# ---------------------------------------------------------------------------
# Register decoding tests
# ---------------------------------------------------------------------------


class TestDecodeRegister:
    """Test register value decoding."""

    def test_u16(self):
        result = RealHuaweiConnector._decode_register([5000], "u16", 10)
        assert result == 500.0

    def test_i16_positive(self):
        result = RealHuaweiConnector._decode_register([3000], "i16", 100)
        assert result == 30.0

    def test_i16_negative(self):
        # -100 as unsigned u16 = 0xFF9C = 65436
        result = RealHuaweiConnector._decode_register([65436], "i16", 10)
        assert result == -10.0

    def test_u32(self):
        # 200,000 = 0x00030D40 → registers [3, 3392]
        result = RealHuaweiConnector._decode_register([3, 3392], "u32", 100)
        assert result == 2000.0

    def test_i32_positive(self):
        result = RealHuaweiConnector._decode_register([0, 5000], "i32", 1000)
        assert result == 5.0

    def test_i32_negative(self):
        # -5000 as u32 = 0xFFFFEC78 → [0xFFFF, 0xEC78] = [65535, 60536]
        result = RealHuaweiConnector._decode_register([65535, 60536], "i32", 1000)
        assert result == -5.0

    def test_str_returns_none(self):
        result = RealHuaweiConnector._decode_register([0x4100, 0x4200], "str", 1)
        assert result is None

    def test_empty_raw_returns_none(self):
        result = RealHuaweiConnector._decode_register([], "u16", 1)
        assert result is None

    def test_u32_insufficient_registers(self):
        result = RealHuaweiConnector._decode_register([100], "u32", 1)
        assert result is None

    def test_scale_zero(self):
        result = RealHuaweiConnector._decode_register([42], "u16", 0)
        assert result == 42.0


class TestDecodeString:
    """Test string register decoding."""

    def test_decode_ascii(self):
        # "AB" = 0x4142
        result = RealHuaweiConnector._decode_string([0x4142, 0x4300], 2)
        assert result == "ABC"

    def test_decode_empty(self):
        result = RealHuaweiConnector._decode_string([], 0)
        assert result == ""


# ---------------------------------------------------------------------------
# Inverter read tests
# ---------------------------------------------------------------------------


class TestReadInverter:
    """Test reading inverter state from mocked Modbus registers."""

    @pytest.mark.asyncio
    async def test_read_inverter_success(self, connector):
        connector._client = _make_mock_client(registers=[5000])
        connector._status.connected = True

        inv = await connector.read_inverter("S002-INV-H01")
        assert inv is not None
        assert inv.inverter_id == "S002-INV-H01"
        assert inv.manufacturer == "Huawei"
        assert inv.protocol == "modbus_tcp"
        assert inv.last_poll is not None

    @pytest.mark.asyncio
    async def test_read_inverter_unknown_id(self, connector):
        connector._client = _make_mock_client()
        connector._status.connected = True

        inv = await connector.read_inverter("UNKNOWN")
        assert inv is None

    @pytest.mark.asyncio
    async def test_read_inverter_with_status_code(self, connector):
        """Verify status code mapping."""
        mock_client = _make_mock_client()
        connector._client = mock_client
        connector._status.connected = True

        # Mock specific register reads — the status register returns 0x0001 (online)
        async def mock_read(address, count=1, slave=1):
            result = MagicMock()
            result.isError.return_value = False
            if address == HUAWEI_SUN2000_REGISTERS["status"][0]:
                result.registers = [0x0001]  # online
            else:
                result.registers = [0] * count
            return result

        mock_client.read_holding_registers = mock_read
        inv = await connector.read_inverter("S002-INV-H01")
        assert inv is not None
        assert inv.status == "online"


# ---------------------------------------------------------------------------
# BESS read tests
# ---------------------------------------------------------------------------


class TestReadBESS:
    """Test reading BESS state from mocked Modbus registers."""

    @pytest.mark.asyncio
    async def test_read_bess_success(self, connector):
        connector._status.connected = True

        # Mock register reads returning specific values
        async def mock_read(address, count=1, slave=1):
            result = MagicMock()
            result.isError.return_value = False
            if address == HUAWEI_LUNA2000_REGISTERS["soc"][0]:
                result.registers = [750]  # 75.0% (scale=10)
            elif address == HUAWEI_LUNA2000_REGISTERS["charge_power"][0]:
                result.registers = [0, 0]  # 0 kW
            elif address == HUAWEI_LUNA2000_REGISTERS["discharge_power"][0]:
                result.registers = [0, 50000]  # 50.0 kW (scale=1000)
            elif address == HUAWEI_LUNA2000_REGISTERS["batt_temp"][0]:
                result.registers = [280]  # 28.0 C
            else:
                result.registers = [0] * count
            return result

        connector._client = MagicMock()
        connector._client.read_holding_registers = mock_read

        bess = await connector.read_bess("S002-BESS-01")
        assert bess is not None
        assert bess.container_id == "S002-BESS-01"
        assert bess.soc_pct == 75.0
        assert bess.discharge_power_kw == 50.0
        assert bess.mode == "discharging"
        assert bess.temp_c == 28.0

    @pytest.mark.asyncio
    async def test_read_bess_no_config(self):
        conn = RealHuaweiConnector(inverters=[], bess=None)
        bess = await conn.read_bess("any")
        assert bess is None

    @pytest.mark.asyncio
    async def test_read_bess_charging_mode(self, connector):
        connector._status.connected = True

        async def mock_read(address, count=1, slave=1):
            result = MagicMock()
            result.isError.return_value = False
            if address == HUAWEI_LUNA2000_REGISTERS["charge_power"][0]:
                result.registers = [0, 30000]  # 30 kW charging
            elif address == HUAWEI_LUNA2000_REGISTERS["discharge_power"][0]:
                result.registers = [0, 0]
            elif address == HUAWEI_LUNA2000_REGISTERS["soc"][0]:
                result.registers = [500]  # 50%
            else:
                result.registers = [0] * count
            return result

        connector._client = MagicMock()
        connector._client.read_holding_registers = mock_read

        bess = await connector.read_bess("S002-BESS-01")
        assert bess is not None
        assert bess.mode == "charging"
        assert bess.charge_power_kw == 30.0


# ---------------------------------------------------------------------------
# Normalised readings tests
# ---------------------------------------------------------------------------


class TestNormalisedReadings:
    """Test get_normalised_readings returns MODBUS source."""

    @pytest.mark.asyncio
    async def test_readings_source_is_modbus(self, connector):
        connector._status.connected = True

        async def mock_read(address, count=1, slave=1):
            result = MagicMock()
            result.isError.return_value = False
            result.registers = [0] * count
            return result

        connector._client = MagicMock()
        connector._client.read_holding_registers = mock_read

        readings = await connector.get_normalised_readings()
        # Should have inverter + BESS readings
        assert len(readings) >= 3  # At least 3 inverter readings
        for r in readings:
            assert r.source == DataSource.MODBUS.value


# ---------------------------------------------------------------------------
# Error handling tests
# ---------------------------------------------------------------------------


class TestErrorHandling:
    """Test graceful error handling."""

    @pytest.mark.asyncio
    async def test_read_registers_not_connected(self, connector):
        connector._status.connected = False
        result = await connector._read_registers(30000, 1)
        assert result is None

    @pytest.mark.asyncio
    async def test_read_registers_modbus_error(self, connector):
        connector._status.connected = True
        connector._client = _make_mock_client(error=True)
        result = await connector._read_registers(30000, 1)
        assert result is None
        assert connector._status.error_count > 0

    @pytest.mark.asyncio
    async def test_read_meter_returns_none(self, connector):
        """Grid meter not implemented for real connector."""
        result = await connector.read_meter("any-meter")
        assert result is None
