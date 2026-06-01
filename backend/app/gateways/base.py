"""SIMBIOTGateway abstract base class."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from app.gateways.schemas import GatewayStatus, SIMBIOTPoint

logger = logging.getLogger(__name__)


class SIMBIOTGateway(ABC):
    """
    Protocol-agnostic gateway abstraction.

    Translates physical device data (BACnet/Modbus/Home Assistant)
    to SENTINEL MQTT topic schemas. Commercial and residential
    deployments both use this interface.

    Gateway implementations:
    - CommercialSIMBIOTGateway: BACnet/Modbus → Mosquitto (Jetson/LattePanda edge)
    - HomeAssistantGateway: HA entity states → Mosquitto (WireGuard tunnel)

    MQTT topic convention:
        sentinel/{site_id}/{sentinel_field}
    """

    def __init__(self, site_id: str, config: dict):
        self.site_id = site_id
        self.config = config
        self._connected = False

    @abstractmethod
    async def connect(self) -> bool:
        """Establish connection to physical devices or network.

        Returns True if connection succeeded, False otherwise.
        """
        ...

    @abstractmethod
    async def get_point_list(self) -> list[SIMBIOTPoint]:
        """Discover available data points from the gateway."""
        ...

    @abstractmethod
    async def subscribe(self) -> None:
        """Begin publishing data to Mosquitto.

        For MQTT-native gateways (HA): subscribes to source topics.
        For polled gateways: starts the polling loop.
        """
        ...

    @abstractmethod
    async def get_status(self) -> GatewayStatus:
        """Current connection and health status."""
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        """Clean shutdown — stop publishing, release resources."""
        ...

    def mqtt_topic(self, sentinel_field: str) -> str:
        """Standard SENTINEL MQTT topic: sentinel/{site_id}/{sentinel_field}."""
        return f"sentinel/{self.site_id}/{sentinel_field}"
