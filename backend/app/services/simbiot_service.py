"""SIMBIOT Concept Evolution Connector Service.

Bridges SENTINEL anomaly detection to MRI Evolution (Concept) via FSI Public API.
Auto-creates work orders when AI detects equipment anomalies or occupants raise requests.
"""

import logging

import httpx

try:
    from simbiot_concept import ConceptConfig, ConceptConnector, SentinelAnomaly
except ImportError:
    ConceptConnector = None  # type: ignore[misc,assignment]
    ConceptConfig = None  # type: ignore[misc,assignment]
    SentinelAnomaly = None  # type: ignore[misc,assignment]

logger = logging.getLogger("sentinel.simbiot")


class SimbiotService:
    """Singleton service wrapping the SIMBIOT ConceptConnector."""

    def __init__(self):
        self._connector: ConceptConnector | None = None
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

    async def upload_document(
        self,
        *,
        file_bytes: bytes,
        filename: str,
        site_id: str,
        metadata: dict,
    ) -> dict:
        """Upload a document to site-network Concept endpoint.

        Uses configured SIMBIOT API credentials. This path is intentionally
        independent of the work-order connector flow so it can operate even
        when the connector package is unavailable.
        """
        from app.config.settings import settings

        if not settings.simbiot_api_url:
            raise RuntimeError("Remote bridge API URL not configured (SIMBIOT_API_URL or BRIDGE_BASE_URL)")
        if not settings.simbiot_api_key and not (settings.simbiot_username and settings.simbiot_password):
            raise RuntimeError(
                "Remote bridge credentials not configured "
                "(SIMBIOT_API_KEY/BRIDGE_API_TOKEN or SIMBIOT_USERNAME+SIMBIOT_PASSWORD)"
            )

        base = settings.simbiot_api_url.rstrip("/")
        url = f"{base}/documents/upload"
        headers = {}
        if settings.simbiot_api_key:
            headers["X-API-Key"] = settings.simbiot_api_key
            headers["Authorization"] = f"Bearer {settings.simbiot_api_key}"

        data = {"site_id": site_id, "metadata": str(metadata)}
        files = {"file": (filename, file_bytes, "application/octet-stream")}

        auth = None
        if settings.simbiot_username and settings.simbiot_password:
            auth = (settings.simbiot_username, settings.simbiot_password)

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, headers=headers, data=data, files=files, auth=auth)
            if resp.status_code not in (200, 201, 202):
                raise RuntimeError(f"SIMBIOT upload failed: HTTP {resp.status_code} {resp.text[:300]}")
            try:
                return resp.json()
            except Exception:
                return {"status": "accepted", "raw_response": resp.text[:500]}

    async def _request_bridge(self, method: str, path: str) -> dict:
        """Call the configured remote site bridge endpoint."""
        from app.config.settings import settings

        if not settings.simbiot_api_url:
            raise RuntimeError("Remote bridge API URL not configured (SIMBIOT_API_URL or BRIDGE_BASE_URL)")
        if not settings.simbiot_api_key and not (settings.simbiot_username and settings.simbiot_password):
            raise RuntimeError(
                "Remote bridge credentials not configured "
                "(SIMBIOT_API_KEY/BRIDGE_API_TOKEN or SIMBIOT_USERNAME+SIMBIOT_PASSWORD)"
            )

        base = settings.simbiot_api_url.rstrip("/")
        url = f"{base}{path}"
        headers: dict[str, str] = {}
        if settings.simbiot_api_key:
            headers["Authorization"] = f"Bearer {settings.simbiot_api_key}"
            headers["X-API-Key"] = settings.simbiot_api_key

        auth = None
        if settings.simbiot_username and settings.simbiot_password:
            auth = (settings.simbiot_username, settings.simbiot_password)

        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.request(method=method, url=url, headers=headers, auth=auth)
            response.raise_for_status()
            return response.json()

    async def get_site_telemetry(self, site_id: str) -> dict:
        """Fetch live site telemetry from the remote bridge."""
        return await self._request_bridge("GET", f"/api/sites/{site_id}/telemetry")

    async def get_site_status(self, site_id: str) -> dict:
        """Fetch live site health/status from the remote bridge."""
        return await self._request_bridge("GET", f"/api/sites/{site_id}/health")

    @property
    def status(self) -> dict:
        if not self._enabled:
            return {"enabled": False, "reason": "not_initialised"}
        return self._connector.status


# Singleton instance
simbiot_service = SimbiotService()
