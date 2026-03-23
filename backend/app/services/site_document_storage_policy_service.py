"""Per-site document storage policy service.

Resolves where technician-uploaded documents should be stored for a site:
- local
- cloud
- site_network

Policy is loaded from JSON and can be updated per customer/site deployment.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from app.config.settings import settings

logger = logging.getLogger(__name__)

DEFAULT_POLICY = {
    "mode": "local",  # local | cloud | site_network
    "dual_write": False,  # if true, write local + remote
    "fallback_to_local": True,  # for site_network mode failures
}


class SiteDocumentStoragePolicyService:
    def __init__(self, policy_path: Path | None = None) -> None:
        self._policy_path = policy_path or (Path(settings.data_dir) / "site_document_storage_policies.json")
        self._cache: dict[str, Any] | None = None

    def _load(self) -> dict[str, Any]:
        if self._cache is not None:
            return self._cache
        if not self._policy_path.exists():
            self._cache = {"default": DEFAULT_POLICY.copy(), "sites": {}}
            return self._cache
        try:
            payload = json.loads(self._policy_path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("policy root must be an object")
            payload.setdefault("default", DEFAULT_POLICY.copy())
            payload.setdefault("sites", {})
            self._cache = payload
            return payload
        except Exception as exc:
            logger.warning("Failed to load site storage policy (%s), using defaults", exc)
            self._cache = {"default": DEFAULT_POLICY.copy(), "sites": {}}
            return self._cache

    def resolve(self, site_id: str, site_code: str | None = None) -> dict[str, Any]:
        payload = self._load()
        default = payload.get("default", DEFAULT_POLICY.copy())
        sites: dict[str, Any] = payload.get("sites", {})
        # Prefer exact site_id, then site_code.
        policy = sites.get(site_id)
        if not policy and site_code:
            policy = sites.get(site_code)
        if not isinstance(policy, dict):
            policy = {}
        resolved = {**default, **policy}
        mode = resolved.get("mode", "local")
        if mode not in {"local", "cloud", "site_network"}:
            resolved["mode"] = "local"
        return resolved


_site_document_storage_policy_service: SiteDocumentStoragePolicyService | None = None


def get_site_document_storage_policy_service() -> SiteDocumentStoragePolicyService:
    global _site_document_storage_policy_service
    if _site_document_storage_policy_service is None:
        _site_document_storage_policy_service = SiteDocumentStoragePolicyService()
    return _site_document_storage_policy_service
