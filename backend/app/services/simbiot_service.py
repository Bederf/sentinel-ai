"""SIMBIOT Concept Evolution Connector Service.

Bridges SENTINEL anomaly detection to MRI Evolution (Concept) via FSI Public API.
Auto-creates work orders when AI detects equipment anomalies or occupants raise requests.
"""

import logging
from typing import Optional

try:
    from simbiot_concept import ConceptConnector, ConceptConfig, SentinelAnomaly
except ImportError:
    ConceptConnector = None  # type: ignore[misc,assignment]
    ConceptConfig = None  # type: ignore[misc,assignment]
    SentinelAnomaly = None  # type: ignore[misc,assignment]

logger = logging.getLogger("sentinel.simbiot")


class SimbiotService:
    """Singleton service wrapping the SIMBIOT ConceptConnector."""

    def __init__(self):
        self._connector: Optional[ConceptConnector] = None
        self._enabled = False

    async def initialise(self, config):
        """Start the connector. Call from FastAPI startup."""
        try:
            if ConceptConnector is None:
                logger.warning("simbiot_concept package not installed — CAFM integration disabled")
                return
            self._connector = ConceptConnector(config)
            await self._connector.initialise()
            self._enabled = True
            logger.info("SIMBIOT Concept connector initialised")
        except Exception as e:
            logger.error(f"SIMBIOT init failed (running without CAFM integration): {e}")
            self._enabled = False

    async def shutdown(self):
        """Stop the connector. Call from FastAPI shutdown."""
        if self._connector:
            await self._connector.shutdown()
            logger.info("SIMBIOT Concept connector shut down")

    async def create_work_order(self, anomaly: SentinelAnomaly):
        """Create a work order from a SENTINEL anomaly."""
        if not self._enabled:
            logger.warning("SIMBIOT not enabled — work order not created")
            return None
        return await self._connector.create_work_order(anomaly)

    @property
    def status(self) -> dict:
        if not self._enabled:
            return {"enabled": False, "reason": "not_initialised"}
        return self._connector.status


# Singleton instance
simbiot_service = SimbiotService()
