"""SIMBIOT onboarding hierarchy ingestion.

Imports native BMS hierarchy evidence into SENTINEL relationship tables while
preserving provenance and confidence. This is the bridge between richer source
systems (Desigo plant/location trees, Niagara station trees, BACnet Structured
Views) and the canonical equipment/zone model used by optimizers.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

EQUIPMENT_RELATIONSHIP_TYPES = {
    "controls",
    "manages",
    "feeds",
    "contains",
    "monitors",
    "parent_of",
    "serves",
    "located_in",
}
ZONE_RELATIONSHIP_TYPES = {"serves", "located_in", "controls", "monitors", "plant"}

RELATIONSHIP_ALIASES = {
    "control": "controls",
    "controlled": "controls",
    "contains": "contains",
    "containment": "contains",
    "child": "contains",
    "parent": "contains",
    "managed_by": "manages",
    "manages": "manages",
    "feeds": "feeds",
    "fed_by": "feeds",
    "serves": "serves",
    "served_by": "serves",
    "located_in": "located_in",
    "location": "located_in",
    "monitors": "monitors",
    "monitored_by": "monitors",
}

SOURCE_DEFAULTS: dict[str, tuple[float, str]] = {
    "desigo_plant_tree": (0.95, "approved"),
    "desigo_location_tree": (0.95, "approved"),
    "bacnet_structured_view": (0.90, "approved"),
    "niagara_station_tree": (0.90, "approved"),
    "bms_tree": (0.90, "approved"),
    "bridge_hierarchy": (0.85, "suggested"),
    "obix_config_hierarchy": (0.85, "suggested"),
    "knx_ets_export": (0.80, "suggested"),
    "modbus_register_map": (0.75, "suggested"),
    "naming_inference": (0.75, "suggested"),
    "manual_onboarding": (0.70, "suggested"),
    "manual_simulation": (0.55, "suggested"),
}


@dataclass
class ResolvedNode:
    source_id: str
    node_type: str
    canonical_code: str | None = None
    zone_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class HierarchyRelationshipPlan:
    parent_source_id: str
    child_source_id: str
    relationship_type: str
    source: str
    confidence: float
    review_status: str
    evidence_basis: str | None
    parent_canonical_code: str | None = None
    child_canonical_code: str | None = None
    equipment_id: str | None = None
    zone_id: str | None = None
    zone_relationship_type: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    skipped_reason: str | None = None


class OnboardingHierarchyService:
    """Import native BMS hierarchy evidence during onboarding."""

    def __init__(self, client: Any | None = None):
        if client is None:
            from app.database.supabase_client import get_supabase_client

            client = get_supabase_client()
        self.client = client

    async def ingest_site_hierarchy(
        self,
        site_id: str,
        *,
        hierarchy: dict[str, Any] | None = None,
        commit: bool = True,
        auto_fetch: bool = True,
    ) -> dict[str, Any]:
        site = self._get_site(site_id)
        site_uuid = site["id"]
        site_code = site.get("code") or site_id

        hierarchy_payload = hierarchy
        fetch_summary: dict[str, Any] = {"attempted": False, "available": hierarchy is not None}
        if hierarchy_payload is None and auto_fetch:
            fetch_summary = await self._fetch_hierarchy_from_adapters(site_code)
            hierarchy_payload = fetch_summary.get("hierarchy")

        if not hierarchy_payload:
            return {
                "site_id": site_code,
                "site_uuid": site_uuid,
                "commit": commit,
                "available": False,
                "source": None,
                "nodes_total": 0,
                "relationships_total": 0,
                "equipment_stubs_created": 0,
                "equipment_relationships_upserted": 0,
                "zone_relationships_upserted": 0,
                "relationships_skipped": 0,
                "review_status_counts": {},
                "fetch": fetch_summary,
                "message": "No native BMS hierarchy available; onboarding should fall back to naming inference/manual mapping.",
            }

        source = _normalize_source(
            hierarchy_payload.get("source") or hierarchy_payload.get("source_type") or "bms_tree"
        )
        nodes = _extract_list(hierarchy_payload, "nodes")
        relationships = _extract_list(hierarchy_payload, "relationships")

        equipment_lookup = self._load_equipment_lookup(site_uuid)
        equipment_stubs_created = 0
        if commit:
            equipment_stubs_created = self._create_missing_equipment_stubs(
                site_uuid,
                nodes,
                equipment_lookup,
                source,
            )
            if equipment_stubs_created:
                equipment_lookup = self._load_equipment_lookup(site_uuid)

        zone_ids = self._load_zone_ids(site_uuid)
        resolved_nodes: dict[str, ResolvedNode] = {
            node_id: resolved
            for node in nodes
            if (node_id := _node_id(node))
            for resolved in [self._resolve_node(node, equipment_lookup, zone_ids)]
        }

        plans = [
            self._plan_relationship(
                relationship,
                source=source,
                resolved_nodes=resolved_nodes,
                equipment_lookup=equipment_lookup,
                zone_ids=zone_ids,
            )
            for relationship in relationships
        ]

        if commit:
            self._apply_plans(site_uuid, plans)
            self._sync_zone_equipment_fields(site_uuid)

        review_counts: dict[str, int] = {}
        for plan in plans:
            if plan.skipped_reason:
                continue
            review_counts[plan.review_status] = review_counts.get(plan.review_status, 0) + 1

        return {
            "site_id": site_code,
            "site_uuid": site_uuid,
            "commit": commit,
            "available": True,
            "source": source,
            "nodes_total": len(nodes),
            "nodes_resolved": sum(1 for node in resolved_nodes.values() if node.canonical_code or node.zone_id),
            "equipment_stubs_created": equipment_stubs_created,
            "relationships_total": len(relationships),
            "equipment_relationships_upserted": sum(
                1
                for plan in plans
                if plan.parent_canonical_code and plan.child_canonical_code and not plan.skipped_reason
            ),
            "zone_relationships_upserted": sum(
                1 for plan in plans if plan.equipment_id and plan.zone_id and not plan.skipped_reason
            ),
            "relationships_skipped": sum(1 for plan in plans if plan.skipped_reason),
            "review_status_counts": review_counts,
            "sample_skipped": [
                {
                    "parent": plan.parent_source_id,
                    "child": plan.child_source_id,
                    "relationship_type": plan.relationship_type,
                    "reason": plan.skipped_reason,
                }
                for plan in plans
                if plan.skipped_reason
            ][:20],
            "fetch": fetch_summary,
        }

    async def _fetch_hierarchy_from_adapters(self, site_id: str) -> dict[str, Any]:
        from app.services.simbiot.bms_adapter import BmsConnectionConfig
        from app.services.site_adapter_manager import SiteAdapterManager

        manager = SiteAdapterManager(self.client)
        configs = manager._fetch_adapter_configs(site_id)
        attempted = 0
        errors: list[dict[str, str]] = []
        for config in configs:
            if not config.get("enabled", False):
                continue
            protocol = str(config.get("protocol") or "bridge")
            connection_config = config.get("connection_config") or {}
            adapter = manager._create_adapter(protocol, site_id, connection_config)
            if adapter is None:
                continue

            attempted += 1
            connect_config = BmsConnectionConfig(
                site_id=site_id,
                source_type=protocol,
                host=connection_config.get("host"),
                port=connection_config.get("port"),
                username=connection_config.get("username"),
                password=connection_config.get("password"),
                use_tls=bool(connection_config.get("use_tls", False)),
                timeout_seconds=float(connection_config.get("timeout_seconds", 10.0)),
                metadata={"token": connection_config.get("token", "")},
            )
            try:
                await adapter.connect(connect_config)
                result = await adapter.discover_hierarchy()
            except Exception as exc:
                errors.append({"protocol": protocol, "error": str(exc)})
                logger.warning("Hierarchy discovery failed for %s/%s: %s", site_id, protocol, exc)
                continue

            if result.get("available") and (result.get("nodes") or result.get("relationships")):
                return {
                    "attempted": True,
                    "available": True,
                    "protocol": protocol,
                    "hierarchy": result,
                    "errors": errors,
                }
            errors.append({"protocol": protocol, "error": result.get("message") or "hierarchy unavailable"})

        return {
            "attempted": attempted > 0,
            "available": False,
            "adapters_checked": attempted,
            "errors": errors,
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

    def _load_equipment_lookup(self, site_uuid: str) -> dict[str, dict[str, str]]:
        response = (
            self.client.table("equipment")
            .select("id, code, raw_code, canonical_code")
            .eq("site_id", site_uuid)
            .execute()
        )
        lookup: dict[str, dict[str, str]] = {}
        for row in response.data or []:
            canonical_code = _preferred_canonical_code(row.get("canonical_code") or row.get("code"))
            if not canonical_code:
                continue
            record = {"id": row["id"], "canonical_code": canonical_code}
            for key in (row.get("code"), row.get("raw_code"), row.get("canonical_code"), canonical_code):
                if key:
                    for alias in _equipment_code_aliases(str(key)):
                        lookup[_norm_key(alias)] = record
                    if "." in str(key):
                        for alias in _equipment_code_aliases(str(key).split(".", 1)[0]):
                            lookup.setdefault(_norm_key(alias), record)

        alias_response = (
            self.client.table("equipment_aliases")
            .select("alias_code, canonical_code")
            .eq("site_id", site_uuid)
            .execute()
        )
        for row in alias_response.data or []:
            alias = row.get("alias_code")
            canonical = _preferred_canonical_code(row.get("canonical_code"))
            if alias and canonical:
                record = lookup.get(_norm_key(canonical), {"id": "", "canonical_code": canonical})
                for key in (*_equipment_code_aliases(canonical), *_equipment_code_aliases(alias)):
                    lookup[_norm_key(key)] = record
        return lookup

    def _create_missing_equipment_stubs(
        self,
        site_uuid: str,
        nodes: list[dict[str, Any]],
        equipment_lookup: dict[str, dict[str, str]],
        source: str,
    ) -> int:
        rows: list[dict[str, Any]] = []
        seen: set[str] = set()
        for node in nodes:
            candidate = _node_equipment_code(node)
            if not candidate or not _is_sentinel_equipment_code(candidate):
                continue

            canonical_code = _preferred_canonical_code(candidate)
            if not canonical_code:
                continue
            if equipment_lookup.get(_norm_key(canonical_code)) or canonical_code in seen:
                continue

            seen.add(canonical_code)
            rows.append(
                {
                    "site_id": site_uuid,
                    "code": canonical_code,
                    "raw_code": candidate,
                    "canonical_code": canonical_code,
                    "canonical_zone_id": _zone_key_from_equipment_code(canonical_code),
                    "name": _equipment_name_from_code(canonical_code),
                    "type": _equipment_type_from_code(canonical_code),
                    "status": "unknown",
                    "canonicalization_status": "needs_review",
                    "canonicalization_source": "hierarchy_ingestion",
                    "canonicalization_metadata": {
                        "source": source,
                        "evidence_basis": node.get("path") or node.get("id") or node.get("name"),
                        "review_status": "suggested",
                        "reason": "native_bms_hierarchy_referenced_missing_equipment",
                    },
                }
            )

        if not rows:
            return 0

        self.client.table("equipment").upsert(rows, on_conflict="code").execute()
        return len(rows)

    def _load_zone_ids(self, site_uuid: str) -> set[str]:
        response = self.client.table("zones").select("zone_id").eq("site_id", site_uuid).execute()
        return {row["zone_id"] for row in response.data or [] if row.get("zone_id")}

    def _resolve_node(
        self,
        node: dict[str, Any],
        equipment_lookup: dict[str, dict[str, str]],
        zone_ids: set[str],
    ) -> ResolvedNode:
        source_id = _node_id(node) or ""
        node_type = str(node.get("type") or node.get("node_type") or "").lower()
        candidates = [
            node.get("canonical_code"),
            node.get("equipment_code"),
            node.get("equipment_id"),
            node.get("code"),
            node.get("id"),
            node.get("name"),
        ]
        canonical_code = None
        for candidate in candidates:
            if not candidate:
                continue
            resolved = equipment_lookup.get(_norm_key(str(candidate)))
            if resolved:
                canonical_code = resolved["canonical_code"]
                break

        zone_id = None
        for candidate in (node.get("zone_id"), node.get("zone_key"), node.get("id"), node.get("name")):
            if candidate and str(candidate) in zone_ids:
                zone_id = str(candidate)
                break

        return ResolvedNode(
            source_id=source_id,
            node_type=node_type,
            canonical_code=canonical_code,
            zone_id=zone_id,
            metadata={"path": node.get("path"), "name": node.get("name")},
        )

    def _plan_relationship(
        self,
        relationship: dict[str, Any],
        *,
        source: str,
        resolved_nodes: dict[str, ResolvedNode],
        equipment_lookup: dict[str, dict[str, str]],
        zone_ids: set[str],
    ) -> HierarchyRelationshipPlan:
        parent_id = _relationship_endpoint(relationship, "parent")
        child_id = _relationship_endpoint(relationship, "child")
        relation_type = _normalize_relationship_type(
            relationship.get("relationship_type") or relationship.get("type") or relationship.get("edge_type")
        )
        evidence_basis = (
            relationship.get("evidence_basis") or relationship.get("path") or relationship.get("source_path")
        )
        relationship_source = _normalize_source(relationship.get("source") or source)
        confidence, review_status = _score_relationship(
            relationship_source,
            relation_type,
            relationship.get("confidence"),
            relationship.get("review_status"),
        )
        metadata = {
            "source": relationship_source,
            "evidence_basis": evidence_basis,
            "raw_relationship": relationship,
        }

        plan = HierarchyRelationshipPlan(
            parent_source_id=parent_id,
            child_source_id=child_id,
            relationship_type=relation_type,
            source=relationship_source,
            confidence=confidence,
            review_status=review_status,
            evidence_basis=str(evidence_basis) if evidence_basis else None,
            metadata=metadata,
        )
        if not parent_id or not child_id:
            plan.skipped_reason = "missing_parent_or_child"
            return plan
        if relation_type not in EQUIPMENT_RELATIONSHIP_TYPES and relation_type not in ZONE_RELATIONSHIP_TYPES:
            plan.skipped_reason = f"unsupported_relationship_type:{relation_type}"
            return plan

        parent = resolved_nodes.get(parent_id) or self._resolve_inline_endpoint(parent_id, equipment_lookup, zone_ids)
        child = resolved_nodes.get(child_id) or self._resolve_inline_endpoint(child_id, equipment_lookup, zone_ids)

        if parent.canonical_code and child.canonical_code and relation_type in EQUIPMENT_RELATIONSHIP_TYPES:
            plan.parent_canonical_code = parent.canonical_code
            plan.child_canonical_code = child.canonical_code
            return plan

        if parent.canonical_code and child.zone_id:
            equipment = equipment_lookup.get(_norm_key(parent.canonical_code))
            plan.equipment_id = equipment.get("id") if equipment else None
            plan.zone_id = child.zone_id
            plan.zone_relationship_type = relation_type if relation_type in ZONE_RELATIONSHIP_TYPES else "serves"
            if not plan.equipment_id:
                plan.skipped_reason = "equipment_row_not_found_for_parent"
            return plan

        if parent.zone_id and child.canonical_code:
            equipment = equipment_lookup.get(_norm_key(child.canonical_code))
            plan.equipment_id = equipment.get("id") if equipment else None
            plan.zone_id = parent.zone_id
            plan.zone_relationship_type = "located_in" if relation_type != "serves" else "serves"
            if not plan.equipment_id:
                plan.skipped_reason = "equipment_row_not_found_for_child"
            return plan

        plan.skipped_reason = "unresolved_parent_or_child"
        return plan

    def _resolve_inline_endpoint(
        self,
        endpoint: str,
        equipment_lookup: dict[str, dict[str, str]],
        zone_ids: set[str],
    ) -> ResolvedNode:
        resolved = equipment_lookup.get(_norm_key(endpoint))
        return ResolvedNode(
            source_id=endpoint,
            node_type="inline",
            canonical_code=resolved["canonical_code"] if resolved else None,
            zone_id=endpoint if endpoint in zone_ids else None,
        )

    def _apply_plans(self, site_uuid: str, plans: list[HierarchyRelationshipPlan]) -> None:
        for plan in plans:
            if plan.skipped_reason:
                continue
            if plan.parent_canonical_code and plan.child_canonical_code:
                self.client.table("equipment_relationships").upsert(
                    {
                        "site_id": site_uuid,
                        "parent_canonical_code": plan.parent_canonical_code,
                        "child_canonical_code": plan.child_canonical_code,
                        "relationship_type": plan.relationship_type,
                        "source": plan.source,
                        "confidence": plan.confidence,
                        "review_status": plan.review_status,
                        "metadata": plan.metadata,
                    },
                    on_conflict="site_id,parent_canonical_code,child_canonical_code,relationship_type",
                ).execute()
            elif plan.equipment_id and plan.zone_id and plan.zone_relationship_type:
                self.client.table("equipment_zone_relationships").upsert(
                    {
                        "site_id": site_uuid,
                        "equipment_id": plan.equipment_id,
                        "zone_id": plan.zone_id,
                        "relationship_type": plan.zone_relationship_type,
                        "source": plan.source,
                        "confidence": plan.confidence,
                        "review_status": plan.review_status,
                        "metadata": plan.metadata,
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


def _extract_list(payload: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = payload.get(key)
    if value is None and isinstance(payload.get("hierarchy"), dict):
        value = payload["hierarchy"].get(key)
    return [item for item in (value or []) if isinstance(item, dict)]


def _node_id(node: dict[str, Any]) -> str | None:
    for key in ("id", "node_id", "source_id", "path", "canonical_code", "equipment_id", "zone_id"):
        value = node.get(key)
        if value:
            return str(value)
    return None


def _node_equipment_code(node: dict[str, Any]) -> str | None:
    for key in ("canonical_code", "equipment_code", "equipment_id", "code", "id", "name"):
        value = node.get(key)
        if value:
            candidate = str(value).strip()
            if _is_sentinel_equipment_code(candidate):
                return candidate
    return None


def _relationship_endpoint(relationship: dict[str, Any], side: str) -> str:
    keys = {
        "parent": ("parent", "parent_id", "source", "source_id", "from", "from_id"),
        "child": ("child", "child_id", "target", "target_id", "to", "to_id"),
    }[side]
    for key in keys:
        value = relationship.get(key)
        if isinstance(value, dict):
            node_id = _node_id(value)
            if node_id:
                return node_id
        elif value:
            return str(value)
    return ""


def _normalize_relationship_type(value: Any) -> str:
    raw = str(value or "contains").strip().lower().replace("-", "_").replace(" ", "_")
    return RELATIONSHIP_ALIASES.get(raw, raw)


def _normalize_source(value: Any) -> str:
    return str(value or "bms_tree").strip().lower().replace("-", "_").replace(" ", "_")


def _score_relationship(
    source: str,
    relationship_type: str,
    explicit_confidence: Any,
    explicit_review_status: Any,
) -> tuple[float, str]:
    default_confidence, default_status = SOURCE_DEFAULTS.get(source, (0.70, "suggested"))
    if source == "niagara_station_tree" and relationship_type == "serves":
        default_confidence, default_status = 0.85, "suggested"

    try:
        confidence = float(explicit_confidence) if explicit_confidence is not None else default_confidence
    except (TypeError, ValueError):
        confidence = default_confidence
    confidence = max(0.0, min(1.0, confidence))

    review_status = str(explicit_review_status or default_status).lower()
    if review_status not in {"suggested", "approved", "rejected"}:
        review_status = default_status
    if (
        review_status != "rejected"
        and confidence >= 0.90
        and source in {"desigo_plant_tree", "desigo_location_tree", "niagara_station_tree", "bacnet_structured_view"}
    ):
        review_status = "approved"
    return confidence, review_status


def _norm_key(value: str) -> str:
    return value.strip().upper()


def _is_sentinel_equipment_code(value: str) -> bool:
    return bool(re.fullmatch(r"S\d{3}-[A-Z0-9_]+-.+", value.strip().upper()))


def _equipment_type_from_code(value: str) -> str:
    match = re.match(r"S\d{3}-([A-Z0-9_]+)-", value.strip().upper())
    if not match:
        return "unknown"
    return match.group(1).lower()


def _zone_key_from_equipment_code(value: str) -> str | None:
    upper = value.strip().upper()
    numeric = re.fullmatch(r"S\d{3}-[A-Z0-9_]+-(\d{3})", upper)
    if numeric:
        return f"Zone-{numeric.group(1)}"

    plant = re.fullmatch(r"S\d{3}-[A-Z0-9_]+-(B\d+|R)-0*(\d+)", upper)
    if plant:
        return f"Zone-{plant.group(1)}-{int(plant.group(2)):03d}"

    floor = re.search(r"-(B\d+|L\d+|R)(?:-|$)", upper)
    if floor:
        return f"Zone-{floor.group(1)}"

    return None


def _equipment_name_from_code(value: str) -> str:
    upper = value.strip().upper()
    parts = upper.split("-")
    if len(parts) < 3:
        return upper
    equipment_type = parts[1]
    suffix = " ".join(parts[2:])
    return f"{equipment_type} {suffix}".strip()


def _preferred_canonical_code(value: Any) -> str | None:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    aliases = _equipment_code_aliases(raw)
    return _choose_preferred_equipment_code(aliases)


def _choose_preferred_equipment_code(values: set[str]) -> str:
    for value in sorted(values):
        if re.fullmatch(r"S\d{3}-[A-Z0-9_]+-(?:B\d+|R)-\d{3}", value):
            return value
    for value in sorted(values):
        if re.fullmatch(r"S\d{3}-[A-Z0-9_]+-\d{3}", value):
            return value
    return sorted(values)[0]


def _equipment_code_aliases(value: str) -> set[str]:
    """Return equivalent equipment-code spellings seen across bridge/catalog data.

    This intentionally handles format aliases only. It does not collapse distinct
    assets such as PUMP-B1-CHW1 into PUMP-B1-001 or CHILLER-B1-002 into
    CHILLER-B1-001.
    """

    raw = value.strip()
    upper = raw.upper()
    aliases = {upper}

    compact = re.fullmatch(r"(S\d{3})-([A-Z0-9_]+)-(B0*\d+|R0*\d+)", upper)
    if compact:
        site, equipment_type, token = compact.groups()
        sequence_match = re.search(r"(\d+)$", token)
        if sequence_match:
            sequence = int(sequence_match.group(1))
            floor = "R" if token.startswith("R") else f"B{sequence}"
            aliases.add(f"{site}-{equipment_type}-{floor}-{sequence:03d}")

    canonical_plant = re.fullmatch(r"(S\d{3})-([A-Z0-9_]+)-(B\d+|R)-0*(\d+)", upper)
    if canonical_plant:
        site, equipment_type, floor, sequence_raw = canonical_plant.groups()
        sequence = int(sequence_raw)
        if floor == "R":
            aliases.add(f"{site}-{equipment_type}-R{sequence:02d}")
        elif floor == f"B{sequence}":
            aliases.add(f"{site}-{equipment_type}-B{sequence:02d}")

    dali_ctrl = re.fullmatch(r"(S\d{3})-DALI-(L\d+)-CTR", upper)
    if dali_ctrl:
        aliases.add(f"{dali_ctrl.group(1)}-DALI-{dali_ctrl.group(2)}-CTRL")

    dali_numeric = re.fullmatch(r"(S\d{3})-DALI-(\d)(\d{2})", upper)
    if dali_numeric:
        site, floor_raw, zone_raw = dali_numeric.groups()
        zone_number = int(zone_raw)
        if 1 <= zone_number <= 26:
            aliases.add(f"{site}-DALI-L{int(floor_raw)}-{chr(ord('A') + zone_number - 1)}")

    dali_letter = re.fullmatch(r"(S\d{3})-DALI-L(\d+)-([A-Z])", upper)
    if dali_letter:
        site, floor_raw, letter = dali_letter.groups()
        zone_number = ord(letter) - ord("A") + 1
        if 1 <= zone_number <= 26:
            aliases.add(f"{site}-DALI-{int(floor_raw)}{zone_number:02d}")

    ground_lighting = re.fullmatch(r"(S\d{3})-LTG-G-(\d{3})", upper)
    if ground_lighting:
        aliases.add(f"{ground_lighting.group(1)}-LTG-{ground_lighting.group(2)}")

    return aliases
