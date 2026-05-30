from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from app.adapters.residential.schemas import AlarmEvent, DeviceManifest, EnergySnapshot


class ResidentialEnergyAdapter(ABC):
    @abstractmethod
    async def authenticate(self) -> bool: ...

    @abstractmethod
    async def discover_devices(self) -> list[DeviceManifest]: ...

    @abstractmethod
    async def get_realtime(self, device_id: str) -> EnergySnapshot: ...

    @abstractmethod
    async def get_historical(
        self, device_id: str, start: datetime, end: datetime
    ) -> list[EnergySnapshot]: ...

    @abstractmethod
    async def get_alarms(self, device_id: str) -> list[AlarmEvent]: ...
