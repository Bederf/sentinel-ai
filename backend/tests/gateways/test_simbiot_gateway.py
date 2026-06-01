"""Tests for SIMBIOTGateway base ABC and schemas."""

from __future__ import annotations

import pytest

from app.gateways.base import SIMBIOTGateway
from app.gateways.schemas import GatewayStatus, SIMBIOTPoint


class TestSIMBIOTPoint:
    def test_dataclass_fields(self):
        p = SIMBIOTPoint(
            point_id="sensor.deye_pv",
            display_name="PV Power",
            unit="W",
            category="energy",
            sentinel_field="energy/pv_power_w",
            gateway_type="home_assistant",
            writable=False,
            site_id="res-123",
            last_value=1500.0,
            last_updated=None,
        )
        assert p.point_id == "sensor.deye_pv"
        assert p.last_value == 1500.0
        assert p.gateway_type == "home_assistant"


class TestGatewayStatus:
    def test_dataclass_fields(self):
        s = GatewayStatus(
            site_id="res-123",
            gateway_type="home_assistant",
            connected=True,
            last_heartbeat=None,
            point_count=5,
            error=None,
        )
        assert s.connected is True
        assert s.point_count == 5
        assert s.error is None


class TestSIMBIOTGatewayABC:
    def test_cannot_instantiate_directly(self):
        """SIMBIOTGateway is abstract — cannot be instantiated."""
        with pytest.raises(TypeError):
            SIMBIOTGateway(site_id="test", config={})

    def test_mqtt_topic(self):
        """mqtt_topic() returns correct sentinel namespace."""

        class DummyGateway(SIMBIOTGateway):
            async def connect(self) -> bool:
                return True

            async def get_point_list(self):
                return []

            async def subscribe(self) -> None:
                pass

            async def get_status(self):
                return GatewayStatus("test", "dummy", False, None, 0)

            async def disconnect(self) -> None:
                pass

        gw = DummyGateway(site_id="res-999", config={})
        assert gw.mqtt_topic("energy/pv_power_w") == "sentinel/res-999/energy/pv_power_w"
        assert gw.mqtt_topic("energy/last_updated") == "sentinel/res-999/energy/last_updated"
