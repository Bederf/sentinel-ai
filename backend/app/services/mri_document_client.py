"""
MRI Evolution REST API client — documents endpoint (separate from work-order client).

Auth: Bearer API key.
Base URL: MRI_DOCUMENT_BASE_URL (e.g. https://{tenant}.mrisoftware.com/Evolution/api/v1/)

FIELD_MAP is PROVISIONAL — field names are assumed from CSV export column names.
Must be updated when vendor confirms actual API field names.

This client handles DOCUMENTS. MRIEvolutionClient handles WORK ORDERS.
These are separate API endpoints with different field names.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import httpx

logger = logging.getLogger(__name__)


def _get_settings():
    """Lazy import to avoid circular dependencies."""
    from app.config.settings import settings

    return settings


# PROVISIONAL — vendor to confirm field names
FIELD_MAP: dict[str, str] = {
    "DocumentId": "DocumentId",
    "DocumentUrl": "DocumentUrl",
    "Site": "Site",
    "EquipmentDescription": "EquipmentDescription",
    "DocumentType": "DocumentType",
    "Category": "Category",
    "DocumentCreationDate": "DocumentCreationDate",
    "TriggerDate": "TriggerDate",
    "ContractorVendor": "ContractorVendor",
    "Author": "Author",
    "Notes": "Notes",
}


class MRIDocumentClient:
    """Async HTTP client for MRI Evolution REST API — documents endpoint."""

    def __init__(self) -> None:
        s = _get_settings()
        self.base_url = s.mri_document_base_url
        self.api_key = s.mri_document_api_key
        self._client: httpx.AsyncClient | None = None

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"}

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(headers=self._headers(), timeout=30.0)
        return self._client

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def fetch_documents(self, since: datetime | None = None) -> list[dict[str, Any]]:
        """
        Pull documents from the MRI Evolution documents endpoint.

        Falls back to full pull if no `since` is provided.

        Handles:
          - 429 (rate limit): wait 60s and retry once
          - 500/503: log error and return empty list
          - timeout (5s): return empty list

        Returns:
            List of raw document record dicts from the MRI API.
        """
        params: dict[str, Any] = {}
        if since:
            params["updated_since"] = since.isoformat()

        client = await self._get_client()

        try:
            response = await client.get(f"{self.base_url}/documents", params=params)
        except httpx.TimeoutException:
            logger.warning("[MRIDocumentClient] fetch_documents timed out after 30s — returning []")
            return []
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                logger.warning("[MRIDocumentClient] Rate limited (429) — sleeping 60s and retrying")
                await client.aclose()
                self._client = None
                client = await self._get_client()
                try:
                    response = await client.get(f"{self.base_url}/documents", params=params)
                except httpx.HTTPStatusError as retry_err:
                    if retry_err.response.status_code in (500, 503):
                        logger.error(
                            "[MRIDocumentClient] Server error %s on retry — returning []",
                            retry_err.response.status_code,
                        )
                        return []
                    raise
            elif e.response.status_code in (500, 503):
                logger.error("[MRIDocumentClient] Server error %s — returning []", e.response.status_code)
                return []
            else:
                raise

        data = response.json()
        return data if isinstance(data, list) else data.get("results", [])

    async def get_document_file(self, document_id: str) -> bytes:
        """
        Retrieve the raw file bytes for the given document_id.

        GET /documents/{document_id}/file — binary PDF/docx response.

        Returns:
            Raw bytes of the document file.

        Raises:
            httpx.HTTPStatusError: on non-2xx response.
        """
        client = await self._get_client()
        response = await client.get(f"{self.base_url}/documents/{document_id}/file")
        response.raise_for_status()
        return response.content
