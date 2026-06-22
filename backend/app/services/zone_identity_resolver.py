"""Shared canonical zone identity resolution.

Zone identifiers arrive from different systems in different shapes. The reflex
layer must not hide that mismatch inside its own matching logic; this resolver
is the single place that turns known aliases into a canonical zone key and
reports unresolved/ambiguous inputs as data-quality gaps.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger("sentinel.zone_identity")

_NUMERIC_ZONE_RE = re.compile(r"^Zone-(\d{3})$", re.IGNORECASE)
_LEVEL_ZONE_RE = re.compile(r"^Zone-L(\d+)-(\d+)$", re.IGNORECASE)


@dataclass(frozen=True)
class ZoneResolution:
    source_zone_id: str
    canonical_zone_id: str | None
    status: str
    reason: str
    aliases: tuple[str, ...] = ()
    provenance: dict[str, Any] = field(default_factory=dict)

    @property
    def resolved(self) -> bool:
        return self.status == "resolved" and bool(self.canonical_zone_id)


class ZoneIdentityResolver:
    """Resolve zone identifiers to one canonical value per site."""

    def __init__(self, *, repository: Any | None = None):
        self.repository = repository or ZoneIdentityRepository()
        self._cache: dict[str, dict[str, ZoneResolution]] = {}

    async def build_site_map(self, site_id: str, *, force_refresh: bool = False) -> dict[str, ZoneResolution]:
        if not force_refresh and site_id in self._cache:
            return self._cache[site_id]

        rows = await self.repository.list_zone_identifiers(site_id)
        identifiers_by_source: dict[str, set[str]] = {}
        for row in rows:
            source = str(row.get("source") or "unknown")
            zone_id = _clean_zone_id(row.get("zone_id"))
            if not zone_id:
                continue
            identifiers_by_source.setdefault(source, set()).add(zone_id)

        equipment_zone_keys = identifiers_by_source.get("equipment.zone_key", set())
        canonical_zone_ids = identifiers_by_source.get("zones", set()) | identifiers_by_source.get("hvac_zones", set())
        all_ids = {zone for zones in identifiers_by_source.values() for zone in zones}
        site_map: dict[str, ZoneResolution] = {}
        for zone_id in sorted(all_ids):
            resolution = self._resolve_from_inventory(
                zone_id,
                canonical_zone_ids,
                equipment_zone_keys,
                identifiers_by_source,
            )
            site_map[zone_id] = resolution

        self._cache[site_id] = site_map
        return site_map

    async def resolve(
        self,
        site_id: str,
        zone_id: str,
        *,
        source_context: str = "unknown",
        record_gap: bool = True,
    ) -> ZoneResolution:
        cleaned = _clean_zone_id(zone_id)
        if not cleaned:
            return ZoneResolution(zone_id, None, "unresolved", "empty_zone_id")

        site_map = await self.build_site_map(site_id)
        resolution = site_map.get(cleaned)
        if not resolution:
            resolution = ZoneResolution(
                source_zone_id=cleaned,
                canonical_zone_id=None,
                status="unresolved",
                reason="zone_id_not_seen_in_site_inventory",
                provenance={"source_context": source_context},
            )

        if record_gap and not resolution.resolved:
            await self.repository.record_resolution_gap(
                site_id=site_id,
                source_zone_id=cleaned,
                source_context=source_context,
                reason=resolution.reason,
                metadata={"provenance": resolution.provenance},
            )
        return resolution

    def _resolve_from_inventory(
        self,
        zone_id: str,
        canonical_zone_ids: set[str],
        equipment_zone_keys: set[str],
        identifiers_by_source: dict[str, set[str]],
    ) -> ZoneResolution:
        if zone_id in canonical_zone_ids:
            return ZoneResolution(
                source_zone_id=zone_id,
                canonical_zone_id=zone_id,
                status="resolved",
                reason="canonical_site_zone_inventory",
                aliases=tuple(sorted(_aliases_for_canonical(zone_id))),
                provenance={"source": "zones_hvac_zones"},
            )

        candidate = _alias_to_canonical_zone(zone_id)
        if candidate and candidate in canonical_zone_ids:
            return ZoneResolution(
                source_zone_id=zone_id,
                canonical_zone_id=candidate,
                status="resolved",
                reason="zone_alias_matches_site_inventory",
                aliases=(zone_id, candidate),
                provenance={"source": "derived", "candidate": candidate},
            )

        if zone_id in identifiers_by_source.get("fcu_zone_state", set()):
            return ZoneResolution(
                source_zone_id=zone_id,
                canonical_zone_id=None,
                status="unresolved",
                reason="fcu_zone_state_zone_not_in_site_zone_inventory",
                provenance={"source": "fcu_zone_state", "candidate": candidate},
            )

        if zone_id in equipment_zone_keys:
            return ZoneResolution(
                source_zone_id=zone_id,
                canonical_zone_id=None,
                status="unresolved",
                reason="equipment_zone_key_not_in_site_zone_inventory",
                provenance={"source": "equipment.zone_key", "candidate": candidate},
            )

        return ZoneResolution(
            source_zone_id=zone_id,
            canonical_zone_id=None,
            status="unresolved",
            reason="no_safe_canonical_zone_mapping",
            provenance={"candidate": candidate, "sources": sorted(identifiers_by_source)},
        )


class ZoneIdentityRepository:
    """Database access for zone identity inventory and gap recording."""

    async def list_zone_identifiers(self, site_id: str) -> list[dict[str, Any]]:
        from app.database.supabase_client import get_async_supabase_client

        client = await get_async_supabase_client()
        site_uuid = await _resolve_site_uuid(client, site_id)
        rows: list[dict[str, Any]] = []

        if site_uuid:
            for table, column, source in (
                ("equipment", "zone_key", "equipment.zone_key"),
                ("hvac_zones", "zone_id", "hvac_zones"),
                ("zones", "zone_id", "zones"),
            ):
                result = await client.table(table).select(column).eq("site_id", site_uuid).execute()
                rows.extend({"source": source, "zone_id": row.get(column)} for row in result.data or [])

        for table, column, source in (
            ("fcu_zone_state", "zone_id", "fcu_zone_state"),
            ("lighting_energy", "zone_id", "lighting_energy"),
            ("zone_occupancy_trigger_events", "zone_id", "zone_occupancy_trigger_events"),
        ):
            result = await client.table(table).select(column).eq("site_id", site_id).limit(5000).execute()
            rows.extend({"source": source, "zone_id": row.get(column)} for row in result.data or [])

        return rows

    async def record_resolution_gap(
        self,
        *,
        site_id: str,
        source_zone_id: str,
        source_context: str,
        reason: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        from app.database.supabase_client import get_async_supabase_client

        client = await get_async_supabase_client()
        await (
            client.table("reflex_zone_resolution_gaps")
            .insert(
                {
                    "site_id": site_id,
                    "source_zone_id": source_zone_id,
                    "source_context": source_context,
                    "reason": reason,
                    "observed_at": datetime.now(UTC).isoformat(),
                    "metadata": metadata or {},
                }
            )
            .execute()
        )


async def _resolve_site_uuid(client: Any, site_id: str) -> str | None:
    if not site_id:
        return None
    if not str(site_id).startswith("site-"):
        return site_id
    result = await client.table("sites").select("id").eq("code", site_id).limit(1).execute()
    if result.data:
        return str(result.data[0].get("id"))
    return None


def _clean_zone_id(value: Any) -> str:
    return str(value or "").strip()


def _numeric_zone_to_level_zone(zone_id: str) -> str | None:
    match = _NUMERIC_ZONE_RE.match(zone_id)
    if not match:
        return None
    raw = match.group(1)
    level = int(raw[0])
    zone_number = int(raw[1:])
    if zone_number <= 0:
        return None
    return f"Zone-L{level}-{zone_number}"


def _level_zone_to_numeric_zone(zone_id: str) -> str | None:
    match = _LEVEL_ZONE_RE.match(zone_id)
    if not match:
        return None
    level = int(match.group(1))
    zone_number = int(match.group(2))
    if zone_number <= 0:
        return None
    return f"Zone-{level}{zone_number:02d}"


def _alias_to_canonical_zone(zone_id: str) -> str | None:
    numeric = _level_zone_to_numeric_zone(zone_id)
    if numeric:
        return numeric
    cleaned = str(zone_id or "").strip()
    if cleaned == "B1":
        return "Zone-B"
    if cleaned.lower() == "roof":
        return "Zone-R"
    return None


def _aliases_for_canonical(zone_id: str) -> set[str]:
    aliases = {zone_id}
    level_alias = _numeric_zone_to_level_zone(zone_id)
    if level_alias:
        aliases.add(level_alias)
    if zone_id == "Zone-B":
        aliases.add("B1")
    if zone_id == "Zone-R":
        aliases.add("Roof")
    return aliases


_resolver: ZoneIdentityResolver | None = None


def get_zone_identity_resolver() -> ZoneIdentityResolver:
    global _resolver
    if _resolver is None:
        _resolver = ZoneIdentityResolver()
    return _resolver
