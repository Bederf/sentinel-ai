"""Base solar connector — abstract interface for manufacturer adapters.

All manufacturer connectors (Huawei, Schneider, SMA, etc.) extend this base class.
Each returns normalised dataclass models regardless of underlying protocol (Modbus TCP,
cloud API, BACnet, etc.).

The simulated variants generate realistic local seeded data following Johannesburg solar curves.
"""

import logging
from abc import ABC, abstractmethod

from app.models.solar import (
    BESSContainer,
    ConnectorStatus,
    GridMeter,
    NormalisedReading,
    SolarInverter,
    SolarString,
)

logger = logging.getLogger(__name__)


class SolarConnector(ABC):
    """Abstract base class for solar/BESS manufacturer connectors.

    Each connector polls a single manufacturer's equipment via its native protocol
    and returns normalised models.  Implementations must handle:
      - Connection management (connect/disconnect)
      - Register reads (Modbus) or API calls (cloud)
      - Unit conversion to SI base units
      - Quality flag assignment
    """

    def __init__(self, manufacturer: str, protocol: str = "modbus_tcp"):
        self.manufacturer = manufacturer
        self.protocol = protocol
        self._status = ConnectorStatus(connected=False)

    # --- lifecycle ---

    @abstractmethod
    async def connect(self) -> bool:
        """Establish connection to the equipment. Returns True on success."""
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        """Cleanly disconnect from the equipment."""
        ...

    # --- reads ---

    @abstractmethod
    async def read_inverter(self, inverter_id: str) -> SolarInverter | None:
        """Read current state of a single inverter."""
        ...

    @abstractmethod
    async def read_all_strings(self, inverter_id: str) -> list[SolarString]:
        """Read all PV strings attached to an inverter."""
        ...

    @abstractmethod
    async def read_bess(self, container_id: str) -> BESSContainer | None:
        """Read current BESS container state (SOC, mode, power, alarms)."""
        ...

    @abstractmethod
    async def read_meter(self, meter_id: str) -> GridMeter | None:
        """Read grid meter readings (import/export, PF, THD)."""
        ...

    @abstractmethod
    async def get_normalised_readings(self) -> list[NormalisedReading]:
        """Poll all registered equipment and return normalised readings."""
        ...

    # --- status ---

    def get_status(self) -> ConnectorStatus:
        """Return current connector health."""
        return self._status

    def is_connected(self) -> bool:
        return self._status.connected
