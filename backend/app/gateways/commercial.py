"""Commercial SIMBIOT Gateway — placeholder stub.

Jetson edge hardware deployment is pending FNB IT BACnet access approval.
This stub logs a warning and returns empty results until the real
BACnet→Mosquitto integration is implemented.
"""

from __future__ import annotations

import logging

from app.gateways.base import SIMBIOTGateway
from app.gateways.schemas import GatewayStatus, SIMBIOTPoint

logger = logging.getLogger(__name__)


class CommercialSIMBIOTGateway(SIMBIOTGateway):
    """
    Placeholder for commercial BACnet/Modbus gateway.

    .. deprecated::
        Jetson edge hardware is pending FNB IT BACnet access approval.
        This stub will be replaced with the real BACnet→Mosquitto
        integration when the edge hardware deploys.

    Currently returns:
    - connect(): False (not connected)
    - get_point_list(): empty list
    - get_status(): error="Not yet deployed"

    Real implementation will:
    - Read BACnet points from Jetson/LattePanda edge device on LAN
    - Normalise to SIMBIOTPoint schema
    - Publish to Mosquitto via paho-mqtt
    """

    def __init__(self, site_id: str, config: dict | None = None):
        super().__init__(site_id, config or {})
        self._logger = logger

    async def connect(self) -> bool:
        self._logger.warning(
            "CommercialSIMBIOTGateway: real BACnet->Mosquitto integration "
            "not yet deployed. Jetson edge hardware is pending FNB IT BACnet "
            "access approval. Returning False."
        )
        self._connected = False
        return False

    async def get_point_list(self) -> list[SIMBIOTPoint]:
        return []

    async def subscribe(self) -> None:
        # No-op until real hardware deploys
        pass

    async def get_status(self) -> GatewayStatus:
        return GatewayStatus(
            site_id=self.site_id,
            gateway_type="bacnet",
            connected=False,
            last_heartbeat=None,
            point_count=0,
            error=("Not yet deployed — Jetson edge hardware pending FNB IT BACnet access approval"),
        )

    async def disconnect(self) -> None:
        self._connected = False
