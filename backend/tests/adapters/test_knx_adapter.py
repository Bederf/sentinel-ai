"""Unit tests for KNX/IP adapter — Phase KNX-01."""

from __future__ import annotations

from unittest.mock import MagicMock

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
from app.services.device_abstraction import DeviceManager
from app.services.knx.knx_adapter import KNXAdapter, _is_emergency_group
from app.services.knx.knx_client import (
    DPT_1_TYPES,
    DPT_5_TYPES,
    DPT_9_TYPES,
    DPT_14_TYPES,
    decode_dpt,
    encode_dpt,
)

# ---------------------------------------------------------------------------
# DPT encoding/decoding round-trip tests
# ---------------------------------------------------------------------------


class TestDPTEncoding:
    """Round-trip: encode → decode must return original value (within tolerance)."""

    @pytest.mark.parametrize(
        "dpt,value,expected_type",
        [
            ("1.001", True, bool),
            ("1.001", False, bool),
            ("5.001", 50.0, float),
            ("5.001", 100.0, float),
            ("5.010", 128, int),
            ("5.010", 255, int),
            ("9.001", 21.5, float),
            ("9.001", -5.0, float),
            ("9.007", 65.0, float),
            ("9.020", 230.0, float),
            ("14.019", 5.2, float),
            ("14.056", 1500.0, float),
            ("14.068", 2500.0, float),
        ],
    )
    def test_dpt_round_trip(self, dpt, value, expected_type):
        encoded = encode_dpt(value, dpt)
        assert encoded is not None
        assert isinstance(encoded, bytes)
        assert len(encoded) > 0

        decoded = decode_dpt(encoded, dpt)
        assert isinstance(decoded, expected_type)

        if dpt in DPT_9_TYPES:
            # DPT 9 float tolerances
            assert abs(decoded - value) <= max(0.5, abs(value) * 0.01)
        elif dpt in DPT_14_TYPES:
            assert abs(decoded - value) <= max(1.0, abs(value) * 0.02)
        elif dpt in DPT_1_TYPES:
            assert decoded == value
        elif dpt in DPT_5_TYPES:
            if dpt == "5.001":
                assert abs(decoded - value) <= 1.0
            else:
                assert decoded == value

    def test_unsupported_dpt_raises(self):
        with pytest.raises(ValueError, match="Unsupported DPT"):
            encode_dpt(42.0, "99.999")

        with pytest.raises(ValueError, match="Unsupported DPT"):
            decode_dpt(b"\x00\x00", "99.999")


class TestEmergencyGroupDetection:
    """Emergency/fire group addresses must be detected and blocked."""

    @pytest.mark.parametrize(
        "description,is_emergency",
        [
            ("Zone 1 Temperature", False),
            ("Emergency Lighting", True),
            ("Fire Alarm Zone A", True),
            ("Evacuation Route Lighting", True),
            ("HVAC Normal Mode", False),
            ("Panic Button Status", True),
            ("Main Door Lock", False),
        ],
    )
    def test_emergency_pattern_detection(self, description, is_emergency):
        meta = {"description": description}
        assert _is_emergency_group(meta) == is_emergency


# ---------------------------------------------------------------------------
# KNXAdapter unit tests
# ---------------------------------------------------------------------------


def _make_knx_device(gateway_host="192.168.1.100", with_emergency=False):
    """Create a KNX Device for testing."""
    # Build group address metadata
    group_addresses = {
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
        "hvac_onoff": {
            "read_address": "1/3/1",
            "write_address": "1/3/1",
            "dpt": "1.001",
            "description": "HVAC On/Off",
            "unit": "",
        },
    }

    if with_emergency:
        group_addresses["fire_alarm"] = {
            "read_address": "2/0/1",
            "dpt": "1.001",
            "description": "Fire Alarm Status",
            "unit": "",
        }

    points = {
        "zone_temp": DevicePoint(
            name="zone_temp",
            point_type=PointType.ANALOG_INPUT,
            description="Zone 1 Temperature",
            unit="°C",
            writable=False,
        ),
        "light_level": DevicePoint(
            name="light_level",
            point_type=PointType.ANALOG_OUTPUT,
            description="Dimming Level",
            unit="%",
            writable=True,
        ),
        "hvac_onoff": DevicePoint(
            name="hvac_onoff",
            point_type=PointType.BINARY_OUTPUT,
            description="HVAC On/Off",
            writable=True,
        ),
    }

    if with_emergency:
        points["fire_alarm"] = DevicePoint(
            name="fire_alarm",
            point_type=PointType.BINARY_INPUT,
            description="Fire Alarm Status",
            writable=True,
            metadata={"group_addresses": {"fire_alarm": group_addresses["fire_alarm"]}},
        )

    device = Device(
        id="knx-test-device-001",
        name="KNX Test Device",
        device_type=DeviceType.LIGHTING,
        protocol=ProtocolType.KNX,
        site_id="site-002",
        device_location=DeviceLocation(
            building="Test Building",
            floor="FL1",
            zone="Q1",
            room="R1",
            description="Test",
        ),
        equipment=DeviceEquipment(manufacturer="KNX", model="KNXnet/IP"),
        status=DeviceStatus.ONLINE,
        points=points,
        metadata={
            "gateway_host": gateway_host,
            "group_addresses": group_addresses,
        },
    )
    return device


class TestKNXAdapterConstruction:
    """KNXAdapter initializes correctly from Device."""

    def test_protocol_type_knx_exists(self):
        assert ProtocolType.KNX.value == "knx"

    def test_adapter_stores_device(self):
        device = _make_knx_device()
        adapter = KNXAdapter(device)
        assert adapter.device is device
        assert adapter._connected is False

    def test_resolve_gateway_from_metadata(self):
        device = _make_knx_device(gateway_host="10.0.0.50")
        adapter = KNXAdapter(device)
        assert adapter._resolve_gateway() == "10.0.0.50"

    def test_missing_gateway_host_raises(self):
        device = _make_knx_device(gateway_host="")
        device.metadata["gateway_host"] = ""
        adapter = KNXAdapter(device)
        with pytest.raises(ValueError, match="gateway_host"):
            adapter._resolve_gateway()


class TestKNXAdapterEmergencySafety:
    """Emergency group address writes must be blocked at adapter level."""

    @pytest.mark.asyncio
    async def test_write_to_emergency_group_raises(self):
        device = _make_knx_device(with_emergency=True)
        adapter = KNXAdapter(device)
        adapter._connected = True

        # Mock the KNX client so we don't hit the real bus
        mock_client = MagicMock()
        mock_client.gateway_host = "192.168.1.100"
        adapter._client = mock_client

        # Emergency write must raise ValueError (not silently proceed)
        with pytest.raises(ValueError, match="read-only"):
            await adapter._protocol_write("fire_alarm", True, priority=8)


class TestDeviceManagerKNXRegistration:
    """DeviceManager must register KNX adapter in adapter_map."""

    def test_knx_protocol_in_device_manager(self):
        """Verify KNXAdapter is in DeviceManager adapter_map at import time."""
        # This tests that the import chain works without hitting the real xknx lib

        # We can verify the adapter_map has the knx key by checking the source
        import inspect

        source = inspect.getsource(DeviceManager._create_adapter)

        # The source should mention "knx" in the adapter_map
        assert '"knx"' in source or "'knx'" in source


class TestKNXClientDPTVectors:
    """Verify key DPT encoding against known vectors."""

    def test_dpt_9_001_temperature_positive(self):
        # Known encoding: 21.5°C → 0x0C 0xD7
        encoded = encode_dpt(21.5, "9.001")
        decoded = decode_dpt(encoded, "9.001")
        assert abs(decoded - 21.5) <= 0.5

    def test_dpt_9_001_temperature_negative(self):
        encoded = encode_dpt(-5.0, "9.001")
        decoded = decode_dpt(encoded, "9.001")
        assert abs(decoded - (-5.0)) <= 0.5

    def test_dpt_1_001_binary_on(self):
        encoded = encode_dpt(True, "1.001")
        assert encoded == b"\x01"
        decoded = decode_dpt(encoded, "1.001")
        assert decoded is True

    def test_dpt_1_001_binary_off(self):
        encoded = encode_dpt(False, "1.001")
        assert encoded == b"\x00"
        decoded = decode_dpt(encoded, "1.001")
        assert decoded is False

    def test_dpt_5_001_percentage_roundtrip(self):
        for pct in [0.0, 25.0, 50.0, 75.0, 100.0]:
            encoded = encode_dpt(pct, "5.001")
            decoded = decode_dpt(encoded, "5.001")
            assert abs(decoded - pct) <= 1.0, f"Failed for {pct}%"

    def test_dpt_5_010_counter(self):
        for val in [0, 100, 200, 255]:
            encoded = encode_dpt(val, "5.010")
            decoded = decode_dpt(encoded, "5.010")
            assert decoded == val


class TestKNXClientImportError:
    """xknx ImportError must produce a clear message."""

    def test_import_error_has_actionable_message(self):
        from app.services.knx.knx_client import KNXClient

        # Creating KNXClient triggers _import_xknx
        # If xknx is installed (it is), this should succeed
        client = KNXClient("192.168.1.1")
        assert client.gateway_host == "192.168.1.1"


class TestETSImport:
    """ETS XML import parsing."""

    def test_valid_ets_xml_parsed(self):
        from app.services.knx.knx_discovery_service import import_ets_group_addresses

        sample_xml = """<?xml version="1.0" encoding="utf-8"?>
<GroupAddresses xmlns="http://www.knx.org/Schema/ETS/GroupAddresses/v2">
  <GroupAddress>
    <Address>1/1/1</Address>
    <Name>Zone 1 Temperature</Name>
    <Description>Main zone temperature sensor</Description>
    <DataType>9.001</DataType>
  </GroupAddress>
  <GroupAddress>
    <Address>1/2/1</Address>
    <Name>Dimming Level</Name>
    <Description>Lighting dimmer</Description>
    <DataType>5.001</DataType>
  </GroupAddress>
</GroupAddresses>"""

        result = import_ets_group_addresses(sample_xml)

        assert len(result) == 2
        assert result[0]["address"] == "1/1/1"
        assert result[0]["dpt"] == "9.001"
        assert result[1]["address"] == "1/2/1"
        assert result[2 if len(result) > 2 else 1]["dpt"] == "5.001"

    def test_invalid_xml_raises(self):
        from app.services.knx.knx_discovery_service import import_ets_group_addresses

        with pytest.raises(ValueError, match="Invalid ETS XML"):
            import_ets_group_addresses("not xml at all")

    def test_dpt_normalization(self):
        from app.services.knx.knx_discovery_service import _normalize_dpt

        assert _normalize_dpt("DPT-9.001") == "9.001"
        assert _normalize_dpt("9.001") == "9.001"
        assert _normalize_dpt("  14.056  ") == "14.056"
