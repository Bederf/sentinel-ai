"""Resolve free-text equipment references to canonical equipment rows."""

from __future__ import annotations

import logging
import re
from typing import Any

from app.database.supabase_client import get_supabase_client
from app.services.asset_id_resolver import AssetIDResolver

logger = logging.getLogger(__name__)


def _site_code_from_reference(reference: str) -> str | None:
    match = re.match(r"^(S\d{3})[-_]", reference.strip().upper())
    if not match:
        return None
    return f"site-{match.group(1)[1:]}"


def _reference_candidates(reference: str) -> list[str]:
    normalized = reference.strip().upper().replace("_", "-")
    candidates = [normalized]
    if normalized.startswith("S") and "-" in normalized:
        tail = normalized.split("-", 1)[1]
        if tail:
            candidates.append(tail.replace("-", " "))
    return candidates


async def resolve_equipment_reference(reference: str, site_id: str | None = None) -> dict[str, Any] | None:
    """Resolve a free-text or partial equipment reference to a canonical equipment row."""
    if not reference or not reference.strip():
        return None

    client = get_supabase_client()
    if not client:
        return None

    normalized = reference.strip().upper().replace("_", "-")

    try:
        exact = (
            client.table("equipment").select("id, code, site_id, type, name").eq("code", normalized).limit(1).execute()
        )
        if exact.data:
            return exact.data[0]
    except Exception:
        logger.debug("Exact equipment lookup failed for %s", reference, exc_info=True)

    resolved_site = site_id or _site_code_from_reference(normalized)
    if not resolved_site:
        return None

    try:
        resolver = AssetIDResolver(client, resolved_site)
        for candidate in _reference_candidates(normalized):
            try:
                result = await resolver.resolve(candidate, document_type="work_order")
            except Exception:
                continue
            if not result.asset_id:
                continue

            matched = (
                client.table("equipment")
                .select("id, code, site_id, type, name")
                .eq("code", result.asset_id)
                .limit(1)
                .execute()
            )
            if matched.data:
                return matched.data[0]
    except Exception:
        logger.debug("Equipment reference resolution failed for %s", reference, exc_info=True)

    return None
