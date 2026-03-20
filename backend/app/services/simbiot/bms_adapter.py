"""Canonical SIMBIOT BMS adapter contract.

This is the building-level integration boundary used by SENTINEL:

    building -> BMS source -> SIMBIOT adapter -> SENTINEL

The contract is intentionally source-agnostic. A live BACnet or oBIX
connection and a lifecycle simulation must both present this same interface
to SENTINEL. SENTINEL should not know whether the upstream source is a real
building BMS or a simulation-backed adapter.

This contract sits above the older per-device `DeviceAdapter` abstraction.
`DeviceAdapter` is still useful for low-level device IO, but SIMBIOT should
integrate against `BmsAdapter` for connection setup, discovery, point reads,
and command transport at the building boundary.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Sequence


@dataclass(slots=True)
class BmsConnectionConfig:
    """Connection details for a building BMS source."""

    site_id: str
    source_type: str
    host: str | None = None
    port: int | None = None
    username: str | None = None
    password: str | None = None
    use_tls: bool = False
    timeout_seconds: float = 10.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class BmsConnectionStatus:
    """Current connection state for a BMS source."""

    connected: bool
    site_id: str
    source_type: str
    status: str
    message: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class BmsAdapterCapabilities:
    """Declared capabilities of a BMS adapter implementation."""

    supports_device_discovery: bool = True
    supports_point_discovery: bool = True
    supports_reads: bool = True
    supports_writes: bool = True
    supports_subscriptions: bool = False
    supports_history: bool = False


@dataclass(slots=True)
class BmsDeviceDescriptor:
    """A BMS-exposed device or logical device boundary."""

    device_id: str
    display_name: str
    protocol: str
    address: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class BmsPointDescriptor:
    """A discovered point that can be read or written through the BMS."""

    point_id: str
    point_name: str
    point_type: str
    unit: str | None = None
    writable: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class BmsPointValue:
    """A point value returned by the adapter."""

    device_id: str
    point_id: str
    value: Any
    quality: str = "good"
    timestamp: str | None = None
    unit: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class BmsWriteRequest:
    """A command issued through the adapter."""

    device_id: str
    point_id: str
    value: Any
    priority: int = 14
    user: str = "system"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class BmsSubscription:
    """Subscription handle for push-style point updates."""

    subscription_id: str
    device_id: str
    point_ids: list[str]
    metadata: dict[str, Any] = field(default_factory=dict)


class BmsAdapter(ABC):
    """Single building/BMS adapter contract for SIMBIOT.

    Implementations:
    - real BMS adapters: BACnet, oBIX, Modbus, Niagara wrappers
    - simulated BMS adapters: lifecycle or other synthetic sources

    SENTINEL should talk only to this interface at the building boundary.
    """

    @property
    @abstractmethod
    def adapter_id(self) -> str:
        """Stable adapter identifier such as `bacnet`, `obix`, or `simulation`."""

    @property
    @abstractmethod
    def capabilities(self) -> BmsAdapterCapabilities:
        """Return the adapter's declared capability set."""

    @abstractmethod
    async def connect(self, config: BmsConnectionConfig) -> BmsConnectionStatus:
        """Connect to the BMS source for the configured building."""

    @abstractmethod
    async def disconnect(self) -> None:
        """Disconnect from the current BMS source."""

    @abstractmethod
    async def get_status(self) -> BmsConnectionStatus:
        """Return current connection state."""

    @abstractmethod
    async def discover_devices(self) -> list[BmsDeviceDescriptor]:
        """Discover devices or logical devices available through the source."""

    @abstractmethod
    async def discover_points(self, device_id: str) -> list[BmsPointDescriptor]:
        """Discover readable or writable points for one device."""

    @abstractmethod
    async def read_point(self, device_id: str, point_id: str) -> BmsPointValue:
        """Read one point value from the source."""

    async def read_points(self, device_id: str, point_ids: Sequence[str]) -> list[BmsPointValue]:
        """Read multiple points from one device.

        Adapters may override this for efficient bulk reads.
        """

        return [await self.read_point(device_id, point_id) for point_id in point_ids]

    @abstractmethod
    async def write_point(self, request: BmsWriteRequest) -> bool:
        """Write one point value to the source."""

    async def subscribe_points(self, device_id: str, point_ids: Sequence[str]) -> BmsSubscription:
        """Create a point subscription if the source supports push updates."""

        raise NotImplementedError(f"{self.adapter_id} does not support subscriptions")

    async def unsubscribe(self, subscription_id: str) -> None:
        """Cancel a point subscription."""

        raise NotImplementedError(f"{self.adapter_id} does not support subscriptions")
