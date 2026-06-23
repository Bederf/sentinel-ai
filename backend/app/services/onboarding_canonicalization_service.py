"""Onboarding equipment and zone canonicalization.

Normalizes vendor/BMS equipment labels into SENTINEL canonical fields while
preserving raw source identifiers. This is the reusable onboarding equivalent
of the S005 backfill migrations.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


SOURCE_ZONE_EQUIPMENT_TYPES = {"FCU", "VAV", "ZONE", "DALI", "LUM"}
SERVING_EQUIPMENT_TYPES = {"AHU", "FCU", "VAV", "SPLIT", "DALI", "LUM", "ZONE"}


@dataclass
class CanonicalizationPlan:
    equipment_id: str
    raw_code: str
    canonical_code: str | None
    canonical_zone_id: str | None
    status: str
    relationship_type: str | None
    alias_type: str | None
    confidence: float
    reason: str
    current_type: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ZoneProposal:
    alias_key: str
    canonical_zone_id: str
    floor: str
    zone_letter: str
    zone_name: str
    reason: str


def site_display_code(site_code: str) -> str:
    value = (site_code or "").strip().upper()
    match = re.search(r"(\d{3})$", value)
    return f"S{match.group(1)}" if match else value


def canonical_zone_from_floor_index(floor_code: str, source_zone: str) -> str | None:
    """Map source floor/index to reserved canonical zone range.

    Floor ranges are reservations, not preallocation. L1 zone 001 maps to
    Zone-100, L1 zone 005 maps to Zone-104, and ground zone 003 maps to
    Zone-003.
    """
    floor = floor_code.strip().upper()
    zone = source_zone.strip().upper()
    if not zone.isdigit():
        return None

    index = int(zone)
    if index <= 0 or index > 99:
        return None

    if floor in {"G", "L0", "0"}:
        zone_number = index
    else:
        floor_match = re.fullmatch(r"L(\d+)", floor)
        if not floor_match:
            return None
        zone_number = int(floor_match.group(1)) * 100 + index - 1

    return f"Zone-{zone_number:03d}"


def source_alias_key(floor_code: str, source_zone: str) -> str:
    floor = floor_code.strip().upper()
    zone = source_zone.strip().upper()
    if floor in {"G", "L0", "0"}:
        floor = "G"
    if zone.isdigit():
        zone = f"{int(zone):03d}"
    return f"Zone-{floor}-{zone}"


def split_canonical_code(code: str) -> tuple[str, str, str] | None:
    match = re.fullmatch(r"(S\d{3})-([A-Z]+)-(\d{3})", code.strip().upper())
    if not match:
        return None
    return match.group(1), match.group(2), match.group(3)


def compact_plant_code(site_prefix: str, equipment_type: str, floor_token: str, sequence: str) -> tuple[str, str]:
    floor = floor_token.strip().upper()
    seq = sequence.strip().upper()
    if floor.startswith("B"):
        floor = f"B{int(floor[1:] or '1')}"
    elif floor == "R":
        floor = "R"
    return (
        f"{site_prefix}-{equipment_type.upper()}-{floor}-{int(seq):03d}",
        f"Zone-{floor}-{int(seq):03d}",
    )


def _equipment_type_from_canonical_code(code: str) -> str | None:
    match = re.fullmatch(r"S\d{3}-([A-Z0-9_]+)-.+", str(code or "").strip().upper())
    if not match:
        return None
    return {
        "CT": "cooling_tower",
        "GEN": "generator",
        "KEF": "exhaust_fan",
        "MEDGAS": "medical_gas",
        "MSB": "switchboard",
        "COLD": "cold_room",
    }.get(match.group(1), match.group(1).lower())


class OnboardingCanonicalizationService:
    """Normalize site equipment after onboarding discovery/import."""

    def __init__(self, client: Any | None = None):
        if client is None:
            from app.database.supabase_client import get_supabase_client

            client = get_supabase_client()
        self.client = client or get_supabase_client()

    def preview_site(self, site_id: str) -> dict[str, Any]:
        return self.canonicalize_site(site_id, commit=False)

    def canonicalize_site(self, site_id: str, *, commit: bool = True) -> dict[str, Any]:
        site = self._get_site(site_id)
        site_uuid = site["id"]
        site_code = site.get("code") or site_id
        site_prefix = site_display_code(site_code)

        zones = self._load_zones(site_uuid)
        aliases = self._load_zone_aliases(site_uuid)
        equipment = self._load_equipment(site_uuid)

        zone_proposals = self._propose_source_zones(equipment, aliases)
        if commit and zone_proposals:
            self._apply_zone_proposals(site_uuid, zone_proposals)
            zones = self._load_zones(site_uuid)
            aliases = self._load_zone_aliases(site_uuid)

        plans = [self._plan_equipment(row, site_prefix=site_prefix, zones=zones, aliases=aliases) for row in equipment]

        if commit:
            for plan in plans:
                self._apply_equipment_plan(site_uuid, plan)
            self._sync_zone_equipment_fields(site_uuid)

        status_counts: dict[str, int] = {}
        for plan in plans:
            status_counts[plan.status] = status_counts.get(plan.status, 0) + 1

        canonicalized = sum(1 for plan in plans if plan.status != "needs_review")
        needs_review = status_counts.get("needs_review", 0)

        return {
            "site_id": site_code,
            "site_uuid": site_uuid,
            "commit": commit,
            "equipment_total": len(equipment),
            "equipment_canonicalized": canonicalized,
            "needs_review": needs_review,
            "status_counts": status_counts,
            "zone_proposals": [proposal.__dict__ for proposal in zone_proposals],
            "zone_proposals_count": len(zone_proposals),
            "sample_review": [
                {
                    "equipment_id": plan.equipment_id,
                    "raw_code": plan.raw_code,
                    "reason": plan.reason,
                }
                for plan in plans
                if plan.status == "needs_review"
            ][:20],
        }

    def _get_site(self, site_id: str) -> dict[str, Any]:
        if re.fullmatch(r"[0-9a-fA-F-]{36}", site_id or ""):
            response = self.client.table("sites").select("id, code, name").eq("id", site_id).limit(1).execute()
            if response.data:
                return response.data[0]

        response = self.client.table("sites").select("id, code, name").eq("code", site_id).limit(1).execute()
        if not response.data:
            raise ValueError(f"Site not found: {site_id}")
        return response.data[0]

    def _load_zones(self, site_uuid: str) -> set[str]:
        response = self.client.table("zones").select("zone_id").eq("site_id", site_uuid).execute()
        return {row["zone_id"] for row in response.data or [] if row.get("zone_id")}

    def _load_zone_aliases(self, site_uuid: str) -> dict[str, str]:
        response = (
            self.client.table("zone_aliases")
            .select("alias_key, canonical_zone_id, review_status")
            .eq("site_id", site_uuid)
            .eq("review_status", "approved")
            .execute()
        )
        return {
            row["alias_key"]: row["canonical_zone_id"]
            for row in response.data or []
            if row.get("alias_key") and row.get("canonical_zone_id")
        }

    def _load_equipment(self, site_uuid: str) -> list[dict[str, Any]]:
        response = (
            self.client.table("equipment")
            .select("id, code, name, type, zone_key, raw_code")
            .eq("site_id", site_uuid)
            .execute()
        )
        return response.data or []

    def _propose_source_zones(
        self,
        equipment: list[dict[str, Any]],
        aliases: dict[str, str],
    ) -> list[ZoneProposal]:
        proposals: dict[str, ZoneProposal] = {}
        for row in equipment:
            parsed = self._parse_raw_source_code(str(row.get("code") or ""))
            if not parsed:
                continue
            equipment_type, floor_code, source_zone, has_point_suffix = parsed
            if has_point_suffix or equipment_type not in SOURCE_ZONE_EQUIPMENT_TYPES:
                continue
            canonical_zone = canonical_zone_from_floor_index(floor_code, source_zone)
            if not canonical_zone:
                continue
            alias_key = source_alias_key(floor_code, source_zone)
            if alias_key in aliases:
                continue
            floor = "L0" if floor_code.upper() in {"G", "L0", "0"} else floor_code.upper()
            proposals[alias_key] = ZoneProposal(
                alias_key=alias_key,
                canonical_zone_id=canonical_zone,
                floor=floor,
                zone_letter=f"{int(source_zone):03d}",
                zone_name=f"{floor} Zone {int(source_zone):03d}",
                reason="inferred_from_source_fcu_vav_or_zone_controller",
            )
        return sorted(proposals.values(), key=lambda proposal: proposal.canonical_zone_id)

    def _apply_zone_proposals(self, site_uuid: str, proposals: list[ZoneProposal]) -> None:
        for proposal in proposals:
            self.client.table("zones").upsert(
                {
                    "site_id": site_uuid,
                    "zone_id": proposal.canonical_zone_id,
                    "zone_name": proposal.zone_name,
                    "floor": proposal.floor,
                    "zone_letter": proposal.zone_letter,
                    "zone_type": "onboarding_inferred",
                },
                on_conflict="site_id,zone_id",
            ).execute()
            self.client.table("zone_aliases").upsert(
                {
                    "site_id": site_uuid,
                    "alias_key": proposal.alias_key,
                    "canonical_zone_id": proposal.canonical_zone_id,
                    "alias_type": "source",
                    "source": "onboarding_canonicalization",
                    "confidence": 0.95,
                    "review_status": "approved",
                    "metadata": {"reason": proposal.reason},
                },
                on_conflict="site_id,alias_key",
            ).execute()

    def _plan_equipment(
        self,
        row: dict[str, Any],
        *,
        site_prefix: str,
        zones: set[str],
        aliases: dict[str, str],
    ) -> CanonicalizationPlan:
        equipment_id = row["id"]
        raw_code = str(row.get("raw_code") or row.get("code") or "")
        code = str(row.get("code") or "")
        current_type = str(row.get("type") or "")
        upper_code = code.upper()

        split = split_canonical_code(upper_code)
        if split:
            _, equipment_type, zone_num = split
            zone_id = f"Zone-{zone_num}"
            if zone_id in zones:
                return CanonicalizationPlan(
                    equipment_id=equipment_id,
                    raw_code=raw_code,
                    canonical_code=upper_code,
                    canonical_zone_id=zone_id,
                    status="canonical",
                    relationship_type="serves" if equipment_type in SERVING_EQUIPMENT_TYPES else "located_in",
                    alias_type=None,
                    confidence=1.0,
                    reason="existing_code_matches_known_canonical_zone",
                    current_type=current_type,
                    metadata={"equipment_type": equipment_type},
                )

        compact_plant = re.fullmatch(rf"{site_prefix}-([A-Z]+)-(B0*\d+|R0*\d+)", upper_code)
        if compact_plant:
            equipment_type = compact_plant.group(1)
            token = compact_plant.group(2)
            floor_token = "R" if token.startswith("R") else token
            sequence = re.search(r"(\d+)$", token)
            if sequence:
                canonical_code, zone_id = compact_plant_code(
                    site_prefix, equipment_type, floor_token, sequence.group(1)
                )
                return CanonicalizationPlan(
                    equipment_id=equipment_id,
                    raw_code=raw_code,
                    canonical_code=canonical_code,
                    canonical_zone_id=zone_id,
                    status="plant_alias",
                    relationship_type="plant",
                    alias_type="legacy",
                    confidence=1.0,
                    reason="compact_plant_code_alias",
                    current_type=current_type,
                    metadata={"equipment_type": equipment_type},
                )

        parsed = self._parse_raw_source_code(code)
        if parsed:
            equipment_type, floor_code, source_zone, has_point_suffix = parsed
            if floor_code.upper() == "R" or floor_code.upper().startswith("B"):
                plant_sequence: str = source_zone if source_zone.isdigit() else "1"
                canonical_code, zone_id = compact_plant_code(site_prefix, equipment_type, floor_code, plant_sequence)
                return CanonicalizationPlan(
                    equipment_id=equipment_id,
                    raw_code=raw_code,
                    canonical_code=canonical_code,
                    canonical_zone_id=zone_id,
                    status="point_level_source" if has_point_suffix else "source_alias",
                    relationship_type="monitors" if has_point_suffix else "plant",
                    alias_type="point_source" if has_point_suffix else "source",
                    confidence=0.95,
                    reason="raw_source_plant_alias_resolved",
                    current_type=current_type,
                    metadata={"has_point_suffix": has_point_suffix},
                )

            alias_key = source_alias_key(floor_code, source_zone)
            canonical_zone = aliases.get(alias_key)
            if canonical_zone and re.fullmatch(r"Zone-\d{3}", canonical_zone):
                zone_num = canonical_zone.split("-")[-1]
                return CanonicalizationPlan(
                    equipment_id=equipment_id,
                    raw_code=raw_code,
                    canonical_code=f"{site_prefix}-{equipment_type}-{zone_num}",
                    canonical_zone_id=canonical_zone,
                    status="point_level_source" if has_point_suffix else "source_alias",
                    relationship_type="monitors" if has_point_suffix else "serves",
                    alias_type="point_source" if has_point_suffix else "source",
                    confidence=0.95,
                    reason="raw_source_zone_alias_resolved",
                    current_type=current_type,
                    metadata={"source_zone_alias": alias_key, "has_point_suffix": has_point_suffix},
                )

        zone_label = re.fullmatch(rf"{site_prefix}-([A-Z]+)-(Zone-.+)", code, flags=re.IGNORECASE)
        if zone_label:
            equipment_type = zone_label.group(1).upper()
            alias_key = zone_label.group(2)
            canonical_zone = aliases.get(alias_key)
            if canonical_zone and re.fullmatch(r"Zone-\d{3}", canonical_zone):
                zone_num = canonical_zone.split("-")[-1]
                return CanonicalizationPlan(
                    equipment_id=equipment_id,
                    raw_code=raw_code,
                    canonical_code=f"{site_prefix}-{equipment_type}-{zone_num}",
                    canonical_zone_id=canonical_zone,
                    status="source_alias",
                    relationship_type="serves" if equipment_type in SERVING_EQUIPMENT_TYPES else "located_in",
                    alias_type="legacy",
                    confidence=0.95,
                    reason="legacy_zone_label_alias_resolved",
                    current_type=current_type,
                    metadata={"source_zone_alias": alias_key},
                )

        return CanonicalizationPlan(
            equipment_id=equipment_id,
            raw_code=raw_code,
            canonical_code=None,
            canonical_zone_id=None,
            status="needs_review",
            relationship_type=None,
            alias_type=None,
            confidence=0.0,
            reason="no_safe_canonical_equipment_mapping",
            current_type=current_type,
        )

    def _parse_raw_source_code(self, code: str) -> tuple[str, str, str, bool] | None:
        m = re.fullmatch(
            r"(?:S\d{3}-)?site-\d{3}-[^-]+-([A-Za-z]+)-(B[0-9]+|R|L[0-9]+|G)-([A-Za-z0-9]+)(?:[.-].*)?",
            code,
        )
        if not m:
            return None
        equipment_type: str = m.group(1).upper()
        floor_code: str = m.group(2).upper()
        source_zone: str = m.group(3).upper()
        has_point_suffix: bool = "." in code
        return equipment_type, floor_code, source_zone, has_point_suffix

    def _apply_equipment_plan(self, site_uuid: str, plan: CanonicalizationPlan) -> None:
        update = {
            "raw_code": plan.raw_code,
            "canonical_code": plan.canonical_code,
            "canonical_zone_id": plan.canonical_zone_id,
            "canonicalization_status": plan.status,
            "canonicalization_source": "onboarding_canonicalization",
            "canonicalization_metadata": {"reason": plan.reason, **plan.metadata},
        }
        if plan.canonical_zone_id:
            update["zone_key"] = plan.canonical_zone_id
        if plan.canonical_code and plan.current_type.lower() in {"", "unknown"}:
            equipment_type = _equipment_type_from_canonical_code(plan.canonical_code)
            if equipment_type:
                update["type"] = equipment_type
        self.client.table("equipment").update(update).eq("id", plan.equipment_id).execute()

        if plan.canonical_code and plan.alias_type:
            self.client.table("equipment_aliases").upsert(
                {
                    "site_id": site_uuid,
                    "equipment_id": plan.equipment_id,
                    "alias_code": plan.raw_code,
                    "canonical_code": plan.canonical_code,
                    "alias_type": plan.alias_type,
                    "source": "onboarding_canonicalization",
                    "confidence": plan.confidence,
                    "review_status": "approved",
                    "metadata": {"reason": plan.reason, **plan.metadata},
                },
                on_conflict="site_id,alias_code",
            ).execute()

        if plan.canonical_zone_id and plan.relationship_type:
            self.client.table("equipment_zone_relationships").upsert(
                {
                    "site_id": site_uuid,
                    "equipment_id": plan.equipment_id,
                    "zone_id": plan.canonical_zone_id,
                    "relationship_type": plan.relationship_type,
                    "source": "onboarding_canonicalization",
                    "confidence": plan.confidence,
                    "review_status": "approved",
                    "metadata": {"reason": plan.reason, **plan.metadata},
                },
                on_conflict="equipment_id,zone_id,relationship_type",
            ).execute()

    def _sync_zone_equipment_fields(self, site_uuid: str) -> None:
        from app.services.zone_equipment_sync_service import ZoneEquipmentSyncService

        result = ZoneEquipmentSyncService(client=self.client).sync_site(site_uuid)
        logger.info(
            "Synced zone equipment fields for %s: %s zones considered, %s zones updated, %s assignments",
            site_uuid,
            result.zones_considered,
            result.zones_updated,
            result.assignments_applied,
        )
