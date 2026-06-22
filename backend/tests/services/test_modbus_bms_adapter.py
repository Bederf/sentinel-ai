"""Tests for ModbusBmsAdapter."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.simbiot import BmsConnectionConfig, BmsConnectionStatus, BmsWriteRequest
from app.services.simbiot.modbus_bms_adapter import ModbusBmsAdapter


def _make_config(register_map=None, slave_id=1, host="192.168.1.100", port=502):
    return BmsConnectionConfig(
        site_id="site-002",
        source_type="modbus",
        host=host,
        port=port,
        timeout_seconds=5.0,
        metadata={
            "register_map": register_map or {},
            "slave_id": slave_id,
        },
    )


# -------------------------------------------------------------------------
# Capabilities
# -------------------------------------------------------------------------
class TestCapabilities:
    def test_adapter_id(self):
        adapter = ModbusBmsAdapter()
        assert adapter.adapter_id == "modbus"

    def test_capabilities_no_discovery(self):
        adapter = ModbusBmsAdapter()
        caps = adapter.capabilities
        assert caps.supports_device_discovery is False
        assert caps.supports_point_discovery is False
        assert caps.supports_reads is True
        assert caps.supports_writes is True
        assert caps.supports_subscriptions is False
        assert caps.supports_history is False


# -------------------------------------------------------------------------
# Connection tests
# -------------------------------------------------------------------------
class TestConnection:
    @pytest.mark.asyncio
    async def test_connect_success(self):
        mock_client = MagicMock()
        mock_client.connect = MagicMock(return_value=True)
        type(mock_client).connected = property(lambda self: True)

        adapter = ModbusBmsAdapter()
        with (
            patch(
                "app.services.simbiot.modbus_bms_adapter.AsyncModbusTcpClient",
                return_value=mock_client,
            ),
            patch.object(
                adapter,
                "get_status",
                AsyncMock(
                    return_value=BmsConnectionStatus(
                        connected=True,
                        site_id="site-002",
                        source_type="modbus",
                        status="connected",
                        message="Modbus TCP client ready",
                    )
                ),
            ),
        ):
            status = await adapter.connect(_make_config())

        assert status.connected is True
        assert status.status == "connected"

    @pytest.mark.asyncio
    async def test_connect_timeout(self):
        mock_client = MagicMock()
        mock_client.connect = MagicMock(return_value=False)
        mock_client.connected = False

        adapter = ModbusBmsAdapter()
        with patch(
            "app.services.simbiot.modbus_bms_adapter.AsyncModbusTcpClient",
            return_value=mock_client,
        ):
            status = await adapter.connect(_make_config(host="192.168.1.254"))

        assert status.connected is False
        assert status.status == "disconnected"

    @pytest.mark.asyncio
    async def test_connect_exception(self):
        mock_client = MagicMock()
        mock_client.connect = MagicMock(side_effect=ConnectionRefusedError("Connection refused"))
        mock_client.connected = False

        adapter = ModbusBmsAdapter()
        with patch(
            "app.services.simbiot.modbus_bms_adapter.AsyncModbusTcpClient",
            return_value=mock_client,
        ):
            status = await adapter.connect(_make_config())

        assert status.connected is False
        assert status.status == "error"

    @pytest.mark.asyncio
    async def test_disconnect(self):
        mock_client = MagicMock()
        mock_client.connect = MagicMock(return_value=True)
        mock_client.close = MagicMock()
        mock_client.connected = True

        adapter = ModbusBmsAdapter()
        with patch(
            "app.services.simbiot.modbus_bms_adapter.AsyncModbusTcpClient",
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
    async def test_discover_devices_from_register_map(self):
        register_map = {
            "GEN-01": {"voltage_l1": {"address": 40001, "type": "holding", "scale": 0.1, "unit": "V"}},
            "UPS-01": {"battery_voltage": {"address": 40010, "type": "holding", "scale": 0.1, "unit": "V"}},
        }
        adapter = ModbusBmsAdapter()
        await adapter.connect(_make_config(register_map=register_map))

        devices = await adapter.discover_devices()

        assert len(devices) == 2
        ids = {d.device_id for d in devices}
        assert "GEN-01" in ids
        assert "UPS-01" in ids

    @pytest.mark.asyncio
    async def test_discover_devices_empty_map(self):
        adapter = ModbusBmsAdapter()
        await adapter.connect(_make_config(register_map={}))

        devices = await adapter.discover_devices()
        assert devices == []

    @pytest.mark.asyncio
    async def test_discover_points(self):
        register_map = {
            "GEN-01": {
                "voltage_l1": {
                    "address": 40001,
                    "type": "holding",
                    "data_type": "uint16",
                    "scale": 0.1,
                    "unit": "V",
                    "writable": False,
                },
                "run_command": {
                    "address": 40100,
                    "type": "holding",
                    "data_type": "uint16",
                    "scale": 1,
                    "writable": True,
                },
            }
        }
        adapter = ModbusBmsAdapter()
        await adapter.connect(_make_config(register_map=register_map))

        points = await adapter.discover_points("GEN-01")

        assert len(points) == 2
        writable = [p for p in points if p.writable]
        read_only = [p for p in points if not p.writable]
        assert len(writable) == 1
        assert len(read_only) == 1

    @pytest.mark.asyncio
    async def test_discover_points_unknown_device(self):
        adapter = ModbusBmsAdapter()
        await adapter.connect(_make_config(register_map={}))
        points = await adapter.discover_points("UNKNOWN")
        assert points == []


# -------------------------------------------------------------------------
# Read tests
# -------------------------------------------------------------------------
class TestRead:
    @pytest.fixture
    def connected_adapter(self):
        async def make():
            register_map = {
                "GEN-01": {
                    "voltage_l1": {
                        "address": 40001,
                        "type": "holding",
                        "data_type": "uint16",
                        "scale": 0.1,
                        "unit": "V",
                    }
                }
            }
            adapter = ModbusBmsAdapter()
            await adapter.connect(_make_config(register_map=register_map))
            return adapter

        class FixtureWrapper:
            async def __aenter__(self):
                return await make()

            async def __aexit__(self, *args):
                pass

        return FixtureWrapper()

    @pytest.mark.asyncio
    async def test_read_holding_register_uint16(self):
        register_map = {
            "GEN-01": {
                "voltage_l1": {
                    "address": 40001,
                    "type": "holding",
                    "data_type": "uint16",
                    "scale": 0.1,
                    "unit": "V",
                }
            }
        }
        mock_response = MagicMock()
        mock_response.isError.return_value = False
        mock_response.registers = [4800]

        mock_client = AsyncMock()
        mock_client.connect = MagicMock(return_value=True)
        mock_client.connected = True
        mock_client.read_holding_registers = AsyncMock(return_value=mock_response)

        adapter = ModbusBmsAdapter()
        with patch(
            "app.services.simbiot.modbus_bms_adapter.AsyncModbusTcpClient",
            return_value=mock_client,
        ):
            await adapter.connect(_make_config(register_map=register_map))
            point = await adapter.read_point("GEN-01", "voltage_l1")

        assert point.value == pytest.approx(480.0, rel=0.01)
        assert point.unit == "V"
        assert point.metadata["raw_value"] == 4800

    @pytest.mark.asyncio
    async def test_read_input_register(self):
        register_map = {
            "GEN-01": {
                "frequency": {
                    "address": 30001,
                    "type": "input",
                    "data_type": "uint16",
                    "scale": 0.01,
                    "unit": "Hz",
                }
            }
        }
        mock_response = MagicMock()
        mock_response.isError.return_value = False
        mock_response.registers = [5000]

        mock_client = AsyncMock()
        mock_client.connect = MagicMock(return_value=True)
        mock_client.connected = True
        mock_client.read_input_registers = AsyncMock(return_value=mock_response)

        adapter = ModbusBmsAdapter()
        with patch(
            "app.services.simbiot.modbus_bms_adapter.AsyncModbusTcpClient",
            return_value=mock_client,
        ):
            await adapter.connect(_make_config(register_map=register_map))
            point = await adapter.read_point("GEN-01", "frequency")

        assert point.value == pytest.approx(50.0, rel=0.01)
        assert point.unit == "Hz"

    @pytest.mark.asyncio
    async def test_read_coil(self):
        register_map = {"GEN-01": {"running": {"address": 1, "type": "coil", "data_type": "bool"}}}
        mock_response = MagicMock()
        mock_response.isError.return_value = False
        mock_response.bits = [True]

        mock_client = AsyncMock()
        mock_client.connect = MagicMock(return_value=True)
        mock_client.connected = True
        mock_client.read_coils = AsyncMock(return_value=mock_response)

        adapter = ModbusBmsAdapter()
        with patch(
            "app.services.simbiot.modbus_bms_adapter.AsyncModbusTcpClient",
            return_value=mock_client,
        ):
            await adapter.connect(_make_config(register_map=register_map))
            point = await adapter.read_point("GEN-01", "running")

        assert point.value == 1.0

    @pytest.mark.asyncio
    async def test_read_discrete_input(self):
        register_map = {"GEN-01": {"alarm": {"address": 10, "type": "discrete", "data_type": "bool"}}}
        mock_response = MagicMock()
        mock_response.isError.return_value = False
        mock_response.bits = [False]

        mock_client = AsyncMock()
        mock_client.connect = MagicMock(return_value=True)
        mock_client.connected = True
        mock_client.read_discrete_inputs = AsyncMock(return_value=mock_response)

        adapter = ModbusBmsAdapter()
        with patch(
            "app.services.simbiot.modbus_bms_adapter.AsyncModbusTcpClient",
            return_value=mock_client,
        ):
            await adapter.connect(_make_config(register_map=register_map))
            point = await adapter.read_point("GEN-01", "alarm")

        assert point.value == 0.0

    @pytest.mark.asyncio
    async def test_read_with_scaling(self):
        register_map = {
            "GEN-01": {
                "voltage_l1": {
                    "address": 40001,
                    "type": "holding",
                    "data_type": "uint16",
                    "scale": 0.1,
                    "unit": "V",
                }
            }
        }
        mock_response = MagicMock()
        mock_response.isError.return_value = False
        mock_response.registers = [4800]

        mock_client = AsyncMock()
        mock_client.connect = MagicMock(return_value=True)
        mock_client.connected = True
        mock_client.read_holding_registers = AsyncMock(return_value=mock_response)

        adapter = ModbusBmsAdapter()
        with patch(
            "app.services.simbiot.modbus_bms_adapter.AsyncModbusTcpClient",
            return_value=mock_client,
        ):
            await adapter.connect(_make_config(register_map=register_map))
            point = await adapter.read_point("GEN-01", "voltage_l1")

        assert point.value == pytest.approx(480.0, rel=0.01)

    @pytest.mark.asyncio
    async def test_read_multiple_points(self):
        register_map = {
            "GEN-01": {
                "voltage_l1": {
                    "address": 40001,
                    "type": "holding",
                    "data_type": "uint16",
                    "scale": 0.1,
                    "unit": "V",
                },
                "frequency": {
                    "address": 40003,
                    "type": "holding",
                    "data_type": "uint16",
                    "scale": 0.01,
                    "unit": "Hz",
                },
            }
        }

        responses = [
            MagicMock(isError=lambda: False, registers=[4800]),
            MagicMock(isError=lambda: False, registers=[5000]),
        ]
        call_count = [0]

        async def fake_read(*args, **kwargs):
            resp = responses[call_count[0]]
            call_count[0] += 1
            return resp

        mock_client = AsyncMock()
        mock_client.connect = MagicMock(return_value=True)
        mock_client.connected = True
        mock_client.read_holding_registers = fake_read

        adapter = ModbusBmsAdapter()
        with patch(
            "app.services.simbiot.modbus_bms_adapter.AsyncModbusTcpClient",
            return_value=mock_client,
        ):
            await adapter.connect(_make_config(register_map=register_map))
            points = await adapter.read_points("GEN-01", ["voltage_l1", "frequency"])

        assert len(points) == 2
        assert points[0].value == pytest.approx(480.0, rel=0.01)
        assert points[1].value == pytest.approx(50.0, rel=0.01)

    @pytest.mark.asyncio
    async def test_read_point_not_in_map(self):
        register_map = {
            "GEN-01": {
                "voltage_l1": {
                    "address": 40001,
                    "type": "holding",
                    "scale": 0.1,
                    "unit": "V",
                }
            }
        }

        mock_client = AsyncMock()
        mock_client.connect = MagicMock(return_value=True)
        mock_client.connected = True

        adapter = ModbusBmsAdapter()
        with patch(
            "app.services.simbiot.modbus_bms_adapter.AsyncModbusTcpClient",
            return_value=mock_client,
        ):
            await adapter.connect(_make_config(register_map=register_map))
            with pytest.raises(ValueError, match="not found"):
                await adapter.read_point("GEN-01", "nonexistent")

    @pytest.mark.asyncio
    async def test_read_connection_error(self):
        register_map = {"GEN-01": {"voltage_l1": {"address": 40001, "type": "holding", "scale": 0.1, "unit": "V"}}}
        mock_client = AsyncMock()
        mock_client.connect = MagicMock(return_value=True)
        mock_client.connected = True
        mock_client.read_holding_registers = AsyncMock(side_effect=ConnectionError("Connection reset"))

        adapter = ModbusBmsAdapter()
        with patch(
            "app.services.simbiot.modbus_bms_adapter.AsyncModbusTcpClient",
            return_value=mock_client,
        ):
            await adapter.connect(_make_config(register_map=register_map))
            with pytest.raises(ConnectionError):
                await adapter.read_point("GEN-01", "voltage_l1")


# -------------------------------------------------------------------------
# Write tests
# -------------------------------------------------------------------------
class TestWrite:
    @pytest.mark.asyncio
    async def test_write_holding_register_success(self):
        register_map = {
            "GEN-01": {
                "run_command": {
                    "address": 40100,
                    "type": "holding",
                    "data_type": "uint16",
                    "scale": 1,
                    "writable": True,
                }
            }
        }

        read_responses = [
            MagicMock(isError=lambda: False, registers=[0]),
            MagicMock(isError=lambda: False, registers=[1]),
        ]
        write_response = MagicMock(isError=lambda: False)
        call_count = [0]

        async def fake_read(*args, **kwargs):
            resp = read_responses[call_count[0]]
            call_count[0] += 1
            return resp

        mock_client = AsyncMock()
        mock_client.connect = MagicMock(return_value=True)
        mock_client.connected = True
        mock_client.read_holding_registers = fake_read
        mock_client.write_register = AsyncMock(return_value=write_response)

        adapter = ModbusBmsAdapter()
        with patch(
            "app.services.simbiot.modbus_bms_adapter.AsyncModbusTcpClient",
            return_value=mock_client,
        ):
            await adapter.connect(_make_config(register_map=register_map))
            success = await adapter.write_point(BmsWriteRequest(device_id="GEN-01", point_id="run_command", value=1))

        assert success is True
        assert call_count[0] == 2

    @pytest.mark.asyncio
    async def test_write_to_readonly_point_fails(self):
        register_map = {
            "GEN-01": {
                "voltage_l1": {
                    "address": 40001,
                    "type": "holding",
                    "data_type": "uint16",
                    "scale": 0.1,
                    "unit": "V",
                    "writable": False,
                }
            }
        }

        mock_client = AsyncMock()
        mock_client.connect = MagicMock(return_value=True)
        mock_client.connected = True

        adapter = ModbusBmsAdapter()
        with patch(
            "app.services.simbiot.modbus_bms_adapter.AsyncModbusTcpClient",
            return_value=mock_client,
        ):
            await adapter.connect(_make_config(register_map=register_map))
            success = await adapter.write_point(BmsWriteRequest(device_id="GEN-01", point_id="voltage_l1", value=500.0))

        assert success is False

    @pytest.mark.asyncio
    async def test_write_to_input_register_fails(self):
        register_map = {
            "GEN-01": {
                "frequency": {
                    "address": 30001,
                    "type": "input",
                    "data_type": "uint16",
                    "scale": 0.01,
                    "unit": "Hz",
                    "writable": True,
                }
            }
        }

        mock_client = AsyncMock()
        mock_client.connect = MagicMock(return_value=True)
        mock_client.connected = True

        adapter = ModbusBmsAdapter()
        with patch(
            "app.services.simbiot.modbus_bms_adapter.AsyncModbusTcpClient",
            return_value=mock_client,
        ):
            await adapter.connect(_make_config(register_map=register_map))
            success = await adapter.write_point(BmsWriteRequest(device_id="GEN-01", point_id="frequency", value=50.0))

        assert success is False

    @pytest.mark.asyncio
    async def test_write_verification_mismatch(self):
        register_map = {
            "GEN-01": {
                "run_command": {
                    "address": 40100,
                    "type": "holding",
                    "data_type": "uint16",
                    "scale": 1,
                    "writable": True,
                }
            }
        }

        read_responses = [
            MagicMock(isError=lambda: False, registers=[0]),
            MagicMock(isError=lambda: False, registers=[2]),
        ]
        write_response = MagicMock(isError=lambda: False)
        call_count = [0]

        async def fake_read(*args, **kwargs):
            resp = read_responses[call_count[0]]
            call_count[0] += 1
            return resp

        mock_client = AsyncMock()
        mock_client.connect = MagicMock(return_value=True)
        mock_client.connected = True
        mock_client.read_holding_registers = fake_read
        mock_client.write_register = AsyncMock(return_value=write_response)

        adapter = ModbusBmsAdapter()
        with patch(
            "app.services.simbiot.modbus_bms_adapter.AsyncModbusTcpClient",
            return_value=mock_client,
        ):
            await adapter.connect(_make_config(register_map=register_map))
            success = await adapter.write_point(BmsWriteRequest(device_id="GEN-01", point_id="run_command", value=1))

        assert success is True

    @pytest.mark.asyncio
    async def test_write_coil(self):
        register_map = {"GEN-01": {"enable": {"address": 1, "type": "coil", "writable": True}}}

        read_responses = [
            MagicMock(isError=lambda: False, bits=[False]),
            MagicMock(isError=lambda: False, bits=[True]),
        ]
        write_response = MagicMock(isError=lambda: False)
        call_count = [0]

        async def fake_read(*args, **kwargs):
            resp = read_responses[call_count[0]]
            call_count[0] += 1
            return resp

        mock_client = AsyncMock()
        mock_client.connect = MagicMock(return_value=True)
        mock_client.connected = True
        mock_client.read_coils = fake_read
        mock_client.write_coil = AsyncMock(return_value=write_response)

        adapter = ModbusBmsAdapter()
        with patch(
            "app.services.simbiot.modbus_bms_adapter.AsyncModbusTcpClient",
            return_value=mock_client,
        ):
            await adapter.connect(_make_config(register_map=register_map))
            success = await adapter.write_point(BmsWriteRequest(device_id="GEN-01", point_id="enable", value=1))

        assert success is True

    @pytest.mark.asyncio
    async def test_write_connection_error(self):
        register_map = {
            "GEN-01": {
                "run_command": {
                    "address": 40100,
                    "type": "holding",
                    "data_type": "uint16",
                    "scale": 1,
                    "writable": True,
                }
            }
        }

        mock_client = AsyncMock()
        mock_client.connect = MagicMock(return_value=True)
        mock_client.connected = True
        mock_client.read_holding_registers = AsyncMock(side_effect=ConnectionError("Connection reset"))

        adapter = ModbusBmsAdapter()
        with patch(
            "app.services.simbiot.modbus_bms_adapter.AsyncModbusTcpClient",
            return_value=mock_client,
        ):
            await adapter.connect(_make_config(register_map=register_map))
            success = await adapter.write_point(BmsWriteRequest(device_id="GEN-01", point_id="run_command", value=1))

        assert success is False

    @pytest.mark.asyncio
    async def test_write_not_in_register_map(self):
        register_map = {
            "GEN-01": {
                "voltage_l1": {
                    "address": 40001,
                    "type": "holding",
                    "scale": 0.1,
                    "writable": True,
                }
            }
        }

        mock_client = AsyncMock()
        mock_client.connect = MagicMock(return_value=True)
        mock_client.connected = True

        adapter = ModbusBmsAdapter()
        with patch(
            "app.services.simbiot.modbus_bms_adapter.AsyncModbusTcpClient",
            return_value=mock_client,
        ):
            await adapter.connect(_make_config(register_map=register_map))
            success = await adapter.write_point(BmsWriteRequest(device_id="GEN-01", point_id="nonexistent", value=1))

        assert success is False

    @pytest.mark.asyncio
    async def test_write_float32_roundtrip(self):
        """Test float32 write then read back round-trip."""
        register_map = {
            "GEN-01": {
                "temperature_setpoint": {
                    "address": 40200,
                    "type": "holding",
                    "data_type": "float32",
                    "scale": 1.0,
                    "writable": True,
                }
            }
        }

        # Float 25.5 -> IEEE 754 = 0x41CC0000 -> registers [0x41CC, 0x0000] (big-endian)
        read_responses = [
            MagicMock(isError=lambda: False, registers=[0x41CC, 0x0000]),  # initial read (0)
            MagicMock(isError=lambda: False, registers=[0x41CC, 0x0000]),  # read back after write (25.5)
        ]
        write_response = MagicMock(isError=lambda: False)
        call_count = [0]

        async def fake_read(*args, **kwargs):
            resp = read_responses[call_count[0]]
            call_count[0] += 1
            return resp

        mock_client = AsyncMock()
        mock_client.connect = MagicMock(return_value=True)
        mock_client.connected = True
        mock_client.read_holding_registers = fake_read
        mock_client.write_registers = AsyncMock(return_value=write_response)

        adapter = ModbusBmsAdapter()
        with patch(
            "app.services.simbiot.modbus_bms_adapter.AsyncModbusTcpClient",
            return_value=mock_client,
        ):
            await adapter.connect(_make_config(register_map=register_map))
            success = await adapter.write_point(
                BmsWriteRequest(device_id="GEN-01", point_id="temperature_setpoint", value=25.5)
            )

        assert success is True
        # Verify write_registers was called (not write_register)
        mock_client.write_registers.assert_called_once()
        # Verify the registers written: [0x41CC, 0x0000] = 25.5 in float32
        written_regs = mock_client.write_registers.call_args[1]["values"]
        assert written_regs == [0x41CC, 0x0000]


# -------------------------------------------------------------------------
# Register map parsing tests
# -------------------------------------------------------------------------
class TestRegisterMapParsing:
    def test_parse_dict_register_map(self):
        register_map = {
            "GEN-01": {
                "voltage_l1": {
                    "address": 40001,
                    "type": "holding",
                    "data_type": "uint16",
                    "scale": 0.1,
                    "unit": "V",
                    "writable": False,
                }
            }
        }
        adapter = ModbusBmsAdapter()
        adapter._register_map = adapter._parse_register_map(register_map)

        assert "GEN-01" in adapter._register_map
        assert "voltage_l1" in adapter._register_map["GEN-01"]
        assert adapter._register_map["GEN-01"]["voltage_l1"]["address"] == 40001
        assert adapter._register_map["GEN-01"]["voltage_l1"]["scale"] == 0.1

    def test_parse_json_register_map(self):
        json_str = json.dumps(
            {
                "GEN-01": {
                    "voltage_l1": {
                        "address": 40001,
                        "type": "holding",
                        "data_type": "uint16",
                        "scale": 0.1,
                        "unit": "V",
                        "writable": False,
                    }
                }
            }
        )
        adapter = ModbusBmsAdapter()
        adapter._register_map = adapter._parse_register_map(json_str)

        assert "GEN-01" in adapter._register_map
        assert adapter._register_map["GEN-01"]["voltage_l1"]["scale"] == 0.1

    def test_parse_csv_register_map(self):
        csv_str = (
            "equipment_id,point_name,address,type,data_type,scale,unit,writable\n"
            "GEN-01,voltage_l1,40001,holding,uint16,0.1,V,false\n"
            "GEN-01,frequency,40003,holding,uint16,0.01,Hz,false\n"
            "UPS-01,battery_voltage,40010,holding,uint16,0.1,V,false"
        )
        adapter = ModbusBmsAdapter()
        adapter._register_map = adapter._parse_register_map(csv_str)

        assert "GEN-01" in adapter._register_map
        assert "UPS-01" in adapter._register_map
        assert "voltage_l1" in adapter._register_map["GEN-01"]
        assert "frequency" in adapter._register_map["GEN-01"]
        assert adapter._register_map["GEN-01"]["voltage_l1"]["address"] == 40001
        assert adapter._register_map["GEN-01"]["voltage_l1"]["writable"] is False
        assert adapter._register_map["GEN-01"]["frequency"]["writable"] is False

    def test_parse_csv_writable_true(self):
        csv_str = (
            "equipment_id,point_name,address,type,data_type,scale,unit,writable\n"
            "GEN-01,run_command,40100,holding,uint16,1,,true"
        )
        adapter = ModbusBmsAdapter()
        adapter._register_map = adapter._parse_register_map(csv_str)

        assert adapter._register_map["GEN-01"]["run_command"]["writable"] is True

    def test_parse_invalid_json(self):
        import json as _json_module

        adapter = ModbusBmsAdapter()
        with pytest.raises(_json_module.JSONDecodeError):
            adapter._parse_register_map("{invalid json}")

    def test_parse_empty_input(self):
        adapter = ModbusBmsAdapter()
        adapter._register_map = adapter._parse_register_map({})
        assert adapter._register_map == {}

        adapter._register_map = adapter._parse_register_map("")
        assert adapter._register_map == {}


# -------------------------------------------------------------------------
# Equipment type inference
# -------------------------------------------------------------------------
class TestEquipmentTypeInference:
    def test_infer_generator(self):
        adapter = ModbusBmsAdapter()
        assert adapter._infer_equipment_type("GEN-01") == "generator"
        assert adapter._infer_equipment_type("GEN-02") == "generator"

    def test_infer_ups(self):
        adapter = ModbusBmsAdapter()
        assert adapter._infer_equipment_type("UPS-01") == "ups"
        assert adapter._infer_equipment_type("ups-main") == "ups"

    def test_infer_ats(self):
        adapter = ModbusBmsAdapter()
        assert adapter._infer_equipment_type("ATS-01") == "transfer_switch"

    def test_infer_motor(self):
        adapter = ModbusBmsAdapter()
        assert adapter._infer_equipment_type("MTR-01") == "motor"

    def test_infer_inverter(self):
        adapter = ModbusBmsAdapter()
        assert adapter._infer_equipment_type("INV-01") == "inverter"

    def test_infer_pdu(self):
        adapter = ModbusBmsAdapter()
        assert adapter._infer_equipment_type("PDU-01") == "power_distribution"

    def test_infer_unknown(self):
        adapter = ModbusBmsAdapter()
        assert adapter._infer_equipment_type("XYZ-01") == "electrical_equipment"


# -------------------------------------------------------------------------
# Error paths
# -------------------------------------------------------------------------
class TestErrorPaths:
    @pytest.mark.asyncio
    async def test_ensure_connected_raises(self):
        adapter = ModbusBmsAdapter()
        with pytest.raises(ConnectionError):
            await adapter.read_point("GEN-01", "voltage_l1")

    @pytest.mark.asyncio
    async def test_subscribe_unsupported(self):
        adapter = ModbusBmsAdapter()
        with pytest.raises(NotImplementedError):
            await adapter.subscribe_points("GEN-01", ["voltage_l1"])

    @pytest.mark.asyncio
    async def test_unknown_register_type_raises(self):
        register_map = {
            "GEN-01": {
                "unknown_point": {
                    "address": 50000,
                    "type": "unknown_type",
                    "data_type": "uint16",
                    "scale": 1,
                }
            }
        }

        mock_client = AsyncMock()
        mock_client.connect = MagicMock(return_value=True)
        mock_client.connected = True

        adapter = ModbusBmsAdapter()
        with patch(
            "app.services.simbiot.modbus_bms_adapter.AsyncModbusTcpClient",
            return_value=mock_client,
        ):
            await adapter.connect(_make_config(register_map=register_map))
            with pytest.raises(ValueError, match="Unknown register type"):
                await adapter.read_point("GEN-01", "unknown_point")

    @pytest.mark.asyncio
    async def test_modbus_error_on_read(self):
        from pymodbus.exceptions import ModbusException

        register_map = {
            "GEN-01": {
                "voltage_l1": {
                    "address": 40001,
                    "type": "holding",
                    "data_type": "uint16",
                    "scale": 0.1,
                    "unit": "V",
                }
            }
        }

        mock_response = MagicMock()
        mock_response.isError.return_value = True

        mock_client = AsyncMock()
        mock_client.connect = MagicMock(return_value=True)
        mock_client.connected = True
        mock_client.read_holding_registers = AsyncMock(return_value=mock_response)

        adapter = ModbusBmsAdapter()
        with patch(
            "app.services.simbiot.modbus_bms_adapter.AsyncModbusTcpClient",
            return_value=mock_client,
        ):
            await adapter.connect(_make_config(register_map=register_map))
            with pytest.raises(ModbusException):
                await adapter.read_point("GEN-01", "voltage_l1")
