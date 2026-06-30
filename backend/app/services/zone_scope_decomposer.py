"""Decompose logical HVAC zone-scope advisories into concrete write targets."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, time, timedelta, timezone
from typing import Any

from app.services.occupancy_fusion_service import get_occupancy_fusion_service
from app.services.sentinel_write_whitelist import get_sentinel_write_whitelist
from app.services.zone_identity_resolver import get_zone_identity_resolver

logger = logging.getLogger("sentinel.zone_scope_decomposer")

ZONE_SCOPE_DECOMPOSITION_RULE = "zone_scope_verified_empty_hvac_shutdown"
PARENT_OCCUPANCY_CONFLICT_RULE = "occupancy_conflict_blocks_hvac_shutdown"
PARENT_CLOSED_EMPTY_HVAC_RULES = {
    "closed_empty_building_hvac_running",
    "after_hours_zero_occupancy_hvac_load",
}

OUTSIDE_HOURS_GENUINE_STAFF_OCCUPANCY_PCT = 35.0
OUTSIDE_HOURS_GENUINE_STAFF_COUNT = 3
OUTSIDE_HOURS_PATROL_MAX_OCCUPANCY_PCT = 10.0
OUTSIDE_HOURS_PATROL_MAX_COUNT = 1
INSIDE_HOURS_OCCUPIED_ZONE_PCT = 5.0
ZONE_SCOPE_STATE_FRESHNESS_MINUTES = 45
HIGH_CO2_PROTECT_PPM = 800.0
SAST = timezone(timedelta(hours=2))


@dataclass(frozen=True)
class ZoneClassification:
    zone_id: str
    classification: str
    occupancy_percent: float | None = None
    occupancy_count: int | None = None
    reason_code: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ZoneEquipmentBinding:
    zone_id: str
    equipment_id: str
    equipment_type: str
    equipment_name: str | None = None


@dataclass(frozen=True)
class WritablePoint:
    equipment_id: str
    point_name: str
    parameter_type: str
    bms_point_id: str | None = None
    mapping_source: str | None = None


@dataclass(frozen=True)
class ZoneScopeDecompositionResult:
    recommendations: list[dict[str, Any]]
    zone_classifications: dict[str, ZoneClassification]
    skipped_equipment: list[dict[str, Any]]
    parent_retained: bool


class ZoneScopeDecomposer:
    """Resolve a logical HVAC zone-scope advisory into safe child recommendations."""

    def __init__(
        self,
        *,
        fusion_service: Any | None = None,
        zone_resolver: Any | None = None,
        whitelist: Any | None = None,
        supabase_client: Any | None = None,
    ):
        self._fusion = fusion_service or get_occupancy_fusion_service()
        self._zone_resolver = zone_resolver or get_zone_identity_resolver()
        self._whitelist = whitelist or get_sentinel_write_whitelist()
        self._sb = supabase_client

    async def decompose(
        self,
        site_id: str,
        logical_advisory: dict[str, Any],
        *,
        current_conditions: dict[str, Any] | None = None,
        fault_gate_context: dict[str, Any] | None = None,
    ) -> ZoneScopeDecompositionResult:
        current_conditions = current_conditions or {}
        supplied = current_conditions.get("zone_scope_decomposition")
        site_uuid = None if isinstance(supplied, dict) else await self._site_uuid(site_id)
        current_time = self._current_time(current_conditions)
        outside_hours = await self._outside_operating_hours(site_id, site_uuid, current_time, current_conditions)

        if isinstance(supplied, dict):
            bindings, writable_points, zone_states = self._load_supplied_context(supplied)
        else:
            bindings = await self._load_zone_equipment_bindings(site_id, site_uuid)
            writable_points = await self._load_verified_writable_points(site_id, site_uuid)
            zone_states = await self._load_zone_states(site_id, bindings)

        zone_ids = sorted({binding.zone_id for binding in bindings})
        if not zone_ids:
            return ZoneScopeDecompositionResult([], {}, [{"reason": "no_zone_equipment_bindings"}], True)

        classifications: dict[str, ZoneClassification] = {}
        for zone_id in zone_ids:
            state = zone_states.get(zone_id, {})
            verdict = await self._get_zone_verdict(site_id, zone_id)
            classifications[zone_id] = self._classify_zone(
                zone_id=zone_id,
                outside_hours=outside_hours,
                verdict=verdict,
                state=state,
            )

        fault_decisions = (fault_gate_context or {}).get("decisions") or {}
        skipped: list[dict[str, Any]] = []
        recs: list[dict[str, Any]] = []
        bindings_by_equipment: dict[str, list[ZoneEquipmentBinding]] = {}
        for binding in bindings:
            bindings_by_equipment.setdefault(binding.equipment_id.upper(), []).append(binding)

        for equipment_id, equipment_bindings in sorted(bindings_by_equipment.items()):
            served_zones = [binding.zone_id for binding in equipment_bindings]
            served_classes = [classifications[z] for z in served_zones if z in classifications]
            if not served_classes:
                skipped.append({"equipment_id": equipment_id, "reason": "no_zone_classification"})
                continue
            if any(item.classification != "verified_empty" for item in served_classes):
                skipped.append(
                    {
                        "equipment_id": equipment_id,
                        "reason": "served_zone_not_verified_empty",
                        "served_zones": served_zones,
                        "classifications": {item.zone_id: item.classification for item in served_classes},
                    }
                )
                continue
            fault_decision = fault_decisions.get(equipment_id) or {}
            if fault_decision.get("suppress"):
                skipped.append(
                    {
                        "equipment_id": equipment_id,
                        "reason": "fault_gate_suppressed",
                        "fault_type": fault_decision.get("fault_type"),
                        "reason_codes": fault_decision.get("reason_codes", []),
                    }
                )
                continue
            point = self._select_writable_point(equipment_id, writable_points.get(equipment_id, []))
            if not point:
                skipped.append({"equipment_id": equipment_id, "reason": "no_verified_whitelisted_writable_point"})
                continue
            recs.append(
                self._build_recommendation(
                    site_id=site_id,
                    logical_advisory=logical_advisory,
                    binding=equipment_bindings[0],
                    point=point,
                    served_zones=served_zones,
                    classifications=served_classes,
                    outside_hours=outside_hours,
                )
            )

        return ZoneScopeDecompositionResult(
            recommendations=recs,
            zone_classifications=classifications,
            skipped_equipment=skipped,
            parent_retained=not bool(recs),
        )

    def _classify_zone(
        self,
        *,
        zone_id: str,
        outside_hours: bool,
        verdict: Any,
        state: dict[str, Any],
    ) -> ZoneClassification:
        occupancy_percent = self._float_or_none(getattr(verdict, "occupancy_percent", None))
        if occupancy_percent is None:
            occupancy_percent = self._float_or_none(state.get("occupancy_pct") or state.get("occupancy_percent"))
        occupancy_count = self._int_or_none(getattr(verdict, "occupancy_count", None))
        is_uncertain = bool(getattr(verdict, "is_uncertain", False))
        is_occupied = bool(getattr(verdict, "is_occupied", False))
        high_co2 = self._zone_has_high_co2(verdict, state)
        evidence = {
            "outside_operating_hours": outside_hours,
            "fused_is_occupied": is_occupied,
            "fused_is_uncertain": is_uncertain,
            "high_co2": high_co2,
            "state": state,
        }

        if high_co2:
            return ZoneClassification(
                zone_id,
                "conflicted_uncertain",
                occupancy_percent,
                occupancy_count,
                "high_co2_protects_zone",
                evidence,
            )

        pct = occupancy_percent if occupancy_percent is not None else 0.0
        count = occupancy_count if occupancy_count is not None else 0
        if outside_hours:
            if pct >= OUTSIDE_HOURS_GENUINE_STAFF_OCCUPANCY_PCT or count >= OUTSIDE_HOURS_GENUINE_STAFF_COUNT:
                return ZoneClassification(
                    zone_id,
                    "verified_occupied",
                    occupancy_percent,
                    occupancy_count,
                    "outside_hours_genuine_staff_presence",
                    evidence,
                )
            return ZoneClassification(
                zone_id,
                "verified_empty",
                occupancy_percent,
                occupancy_count,
                "outside_hours_below_genuine_staff_threshold",
                evidence,
            )

        if is_uncertain:
            return ZoneClassification(
                zone_id,
                "conflicted_uncertain",
                occupancy_percent,
                occupancy_count,
                "inside_hours_uncertain_fails_safe",
                evidence,
            )
        if is_occupied or pct > INSIDE_HOURS_OCCUPIED_ZONE_PCT or count > 0:
            return ZoneClassification(
                zone_id,
                "verified_occupied",
                occupancy_percent,
                occupancy_count,
                "inside_hours_occupied_zone",
                evidence,
            )
        return ZoneClassification(
            zone_id,
            "verified_empty",
            occupancy_percent,
            occupancy_count,
            "inside_hours_zone_empty",
            evidence,
        )

    def _build_recommendation(
        self,
        *,
        site_id: str,
        logical_advisory: dict[str, Any],
        binding: ZoneEquipmentBinding,
        point: WritablePoint,
        served_zones: list[str],
        classifications: list[ZoneClassification],
        outside_hours: bool,
    ) -> dict[str, Any]:
        value = self._target_value_for_point(point.point_name)
        action_label = self._action_label(point.point_name, value)
        parent_metadata = logical_advisory.get("metadata") or {}
        parent_rule = parent_metadata.get("rule") or PARENT_OCCUPANCY_CONFLICT_RULE
        parent_target = logical_advisory.get("target_equipment") or logical_advisory.get("equipment_id")
        supersedes_rules = {
            PARENT_OCCUPANCY_CONFLICT_RULE,
            *PARENT_CLOSED_EMPTY_HVAC_RULES,
            parent_rule,
        }
        return {
            "equipment_id": binding.equipment_id,
            "equipment_name": binding.equipment_name or binding.equipment_id,
            "target_equipment": binding.equipment_id,
            "point_name": point.point_name,
            "current_value": None,
            "recommended_value": value,
            "unit": self._unit_for_point(point.point_name),
            "system": "hvac",
            "action_type": "ai_optimization",
            "action": {
                "point": point.point_name,
                "value": value,
                "execution_blocked": False,
            },
            "confidence": 0.74 if outside_hours else 0.68,
            "savings_kwh": 0.0,
            "reason": (
                f"{binding.equipment_id} serves verified-empty zone(s) {', '.join(served_zones)}. "
                f"{action_label} while leaving occupied, high-CO2, or conflicted zones untouched."
            ),
            "metadata": {
                "rule": ZONE_SCOPE_DECOMPOSITION_RULE,
                "logical_family": "site_hvac_after_hours_operating_state",
                "advisory_type": "zone_scope_concrete_hvac_action",
                "parent_rule": parent_rule,
                "parent_target_equipment": parent_target,
                "supersedes_rules": sorted(supersedes_rules),
                "superseded_by_rule": ZONE_SCOPE_DECOMPOSITION_RULE,
                "outside_operating_hours": outside_hours,
                "served_zones": served_zones,
                "zone_classifications": {
                    item.zone_id: {
                        "classification": item.classification,
                        "reason_code": item.reason_code,
                        "occupancy_percent": item.occupancy_percent,
                        "occupancy_count": item.occupancy_count,
                    }
                    for item in classifications
                },
                "point_resolution": {
                    "raw": point.point_name,
                    "resolved": point.point_name,
                    "method": "zone_scope_decomposer_verified_mapping",
                    "confidence": "verified",
                    "bms_point_id": point.bms_point_id,
                    "parameter_type": point.parameter_type,
                    "mapping_source": point.mapping_source,
                },
                "thresholds": {
                    "outside_hours_genuine_staff_occupancy_pct": OUTSIDE_HOURS_GENUINE_STAFF_OCCUPANCY_PCT,
                    "outside_hours_genuine_staff_count": OUTSIDE_HOURS_GENUINE_STAFF_COUNT,
                    "inside_hours_occupied_zone_pct": INSIDE_HOURS_OCCUPIED_ZONE_PCT,
                },
                "source_metadata": parent_metadata,
                "site_id": site_id,
            },
            "point_resolution": {
                "raw": point.point_name,
                "resolved": point.point_name,
                "method": "zone_scope_decomposer_verified_mapping",
                "confidence": "verified",
                "bms_point_id": point.bms_point_id,
                "parameter_type": point.parameter_type,
                "mapping_source": point.mapping_source,
            },
        }

    async def _get_zone_verdict(self, site_id: str, zone_id: str) -> Any:
        return await self._fusion.get_fused_occupancy(site_id, zone_id=zone_id, force_refresh=True)

    async def _load_zone_equipment_bindings(self, site_id: str, site_uuid: str | None) -> list[ZoneEquipmentBinding]:
        if not site_uuid:
            return []
        sb = self._client()
        zone_rows = (
            sb.table("zones").select("zone_id,fcu_id,vav_id,ahu_id").eq("site_id", site_uuid).execute().data or []
        )
        equipment_rows = (
            sb.table("equipment")
            .select("code,type,name,zone_key,canonical_zone_id")
            .eq("site_id", site_uuid)
            .execute()
            .data
            or []
        )
        equipment_by_code = {str(row.get("code") or "").upper(): row for row in equipment_rows if row.get("code")}
        bindings: dict[tuple[str, str], ZoneEquipmentBinding] = {}

        for row in zone_rows:
            zone_id = await self._canonical_zone_id(site_id, row.get("zone_id"))
            if not zone_id:
                continue
            for key in ("fcu_id", "vav_id", "ahu_id"):
                code = str(row.get(key) or "").strip().upper()
                if code:
                    eq = equipment_by_code.get(code, {})
                    bindings[(zone_id, code)] = ZoneEquipmentBinding(
                        zone_id=zone_id,
                        equipment_id=code,
                        equipment_type=str(eq.get("type") or key[:3]).lower(),
                        equipment_name=eq.get("name"),
                    )

        for row in equipment_rows:
            eq_type = str(row.get("type") or "").lower()
            if eq_type not in {"ahu", "fcu", "vav"}:
                continue
            code = str(row.get("code") or "").strip().upper()
            zone_key = row.get("canonical_zone_id") or row.get("zone_key")
            zone_id = await self._canonical_zone_id(site_id, zone_key)
            if code and zone_id:
                bindings[(zone_id, code)] = ZoneEquipmentBinding(
                    zone_id=zone_id,
                    equipment_id=code,
                    equipment_type=eq_type,
                    equipment_name=row.get("name"),
                )
        return list(bindings.values())

    async def _load_verified_writable_points(
        self, site_id: str, site_uuid: str | None
    ) -> dict[str, list[WritablePoint]]:
        if not site_uuid:
            return {}
        sb = self._client()
        rows = (
            sb.table("point_asset_mappings")
            .select("extracted_asset_id,bms_point_id,parameter_name,parameter_type,mapping_source")
            .eq("site_id", site_uuid)
            .eq("is_verified", True)
            .execute()
            .data
            or []
        )
        result: dict[str, list[WritablePoint]] = {}
        for row in rows:
            equipment_id = str(row.get("extracted_asset_id") or "").strip().upper()
            point_name = str(row.get("parameter_name") or "").strip()
            parameter_type = str(row.get("parameter_type") or "").strip()
            if not equipment_id or not point_name or not self._parameter_type_is_writable(parameter_type):
                continue
            if not self._whitelist.can_write(equipment_id, point_name).allowed:
                continue
            result.setdefault(equipment_id, []).append(
                WritablePoint(
                    equipment_id=equipment_id,
                    point_name=point_name,
                    parameter_type=parameter_type,
                    bms_point_id=row.get("bms_point_id"),
                    mapping_source=row.get("mapping_source"),
                )
            )
        return result

    async def _load_zone_states(
        self,
        site_id: str,
        bindings: list[ZoneEquipmentBinding],
    ) -> dict[str, dict[str, Any]]:
        sb = self._client()
        rows = (
            sb.table("fcu_zone_state")
            .select("zone_id,occupancy_pct,room_temp_c,setpoint_c,fcu_inferred_running,occupancy_source,timestamp")
            .eq("site_id", site_id)
            .order("timestamp", desc=True)
            .limit(500)
            .execute()
            .data
            or []
        )
        states: dict[str, dict[str, Any]] = {}
        for row in rows:
            zone_id = await self._canonical_zone_id(site_id, row.get("zone_id"))
            if not zone_id or zone_id in states:
                continue
            if self._is_stale(row.get("timestamp")):
                continue
            states[zone_id] = dict(row)

        equipment_to_zones: dict[str, set[str]] = {}
        for binding in bindings:
            equipment_to_zones.setdefault(binding.equipment_id, set()).add(binding.zone_id)
        prefix = site_id.upper().replace("SITE-", "S")
        zone_sensor_to_zone: dict[str, str] = {
            f"{prefix}-ZONE-{zone_id.rsplit('-', 1)[-1]}": zone_id
            for zone_id in {binding.zone_id for binding in bindings}
            if zone_id.upper().startswith("ZONE-")
        }
        if zone_sensor_to_zone:
            direct_rows = (
                sb.table("equipment_sensor_readings")
                .select("equipment_id,sensor_type,value,recorded_at")
                .eq("site_id", site_id)
                .eq("sensor_type", "co2_ppm")
                .in_("equipment_id", sorted(zone_sensor_to_zone))
                .order("recorded_at", desc=True)
                .limit(500)
                .execute()
                .data
                or []
            )
            seen_direct: set[str] = set()
            for row in direct_rows:
                equipment_id = str(row.get("equipment_id") or "").upper()
                if equipment_id in seen_direct or self._is_stale(row.get("recorded_at"), minutes=30):
                    continue
                seen_direct.add(equipment_id)
                zone_id = zone_sensor_to_zone.get(equipment_id)
                if not zone_id:
                    continue
                states.setdefault(zone_id, {})["co2_ppm"] = self._float_or_none(row.get("value"))
                states[zone_id]["co2_recorded_at"] = row.get("recorded_at")
                states[zone_id]["co2_source"] = "direct_zone_sensor"

        equipment_ids = sorted(equipment_to_zones)
        if equipment_ids:
            co2_rows = (
                sb.table("equipment_sensor_readings")
                .select("equipment_id,sensor_type,value,recorded_at")
                .eq("site_id", site_id)
                .eq("sensor_type", "co2_ppm")
                .in_("equipment_id", equipment_ids)
                .order("recorded_at", desc=True)
                .limit(500)
                .execute()
                .data
                or []
            )
            seen_equipment: set[str] = set()
            for row in co2_rows:
                equipment_id = str(row.get("equipment_id") or "").upper()
                if equipment_id in seen_equipment or self._is_stale(row.get("recorded_at"), minutes=30):
                    continue
                seen_equipment.add(equipment_id)
                for zone_id in equipment_to_zones.get(equipment_id, set()):
                    if states.get(zone_id, {}).get("co2_source") == "direct_zone_sensor":
                        continue
                    states.setdefault(zone_id, {})["co2_ppm"] = self._float_or_none(row.get("value"))
                    states[zone_id]["co2_recorded_at"] = row.get("recorded_at")
                    states[zone_id]["co2_source"] = "served_equipment_sensor"
        return states

    def _load_supplied_context(
        self,
        supplied: dict[str, Any],
    ) -> tuple[list[ZoneEquipmentBinding], dict[str, list[WritablePoint]], dict[str, dict[str, Any]]]:
        bindings = [
            ZoneEquipmentBinding(
                zone_id=str(row["zone_id"]),
                equipment_id=str(row["equipment_id"]).upper(),
                equipment_type=str(row.get("equipment_type") or "").lower(),
                equipment_name=row.get("equipment_name"),
            )
            for row in supplied.get("bindings", [])
        ]
        writable: dict[str, list[WritablePoint]] = {}
        for row in supplied.get("writable_points", []):
            point = WritablePoint(
                equipment_id=str(row["equipment_id"]).upper(),
                point_name=str(row["point_name"]),
                parameter_type=str(row.get("parameter_type") or "command"),
                bms_point_id=row.get("bms_point_id"),
                mapping_source=row.get("mapping_source"),
            )
            writable.setdefault(point.equipment_id, []).append(point)
        states = {str(zone_id): dict(state) for zone_id, state in (supplied.get("zone_states") or {}).items()}
        return bindings, writable, states

    async def _site_uuid(self, site_id: str) -> str | None:
        try:
            result = self._client().table("sites").select("id").eq("code", site_id).limit(1).execute()
            return str(result.data[0]["id"]) if result.data else None
        except Exception as exc:
            logger.warning("Could not resolve site UUID for %s: %s", site_id, exc)
            return None

    async def _outside_operating_hours(
        self,
        site_id: str,
        site_uuid: str | None,
        current_time: datetime,
        current_conditions: dict[str, Any],
    ) -> bool:
        schedule = current_conditions.get("operating_hours") or current_conditions.get("schedule")
        if not schedule and site_uuid:
            try:
                result = self._client().table("sites").select("operating_hours").eq("id", site_uuid).limit(1).execute()
                if result.data:
                    schedule = result.data[0].get("operating_hours")
            except Exception as exc:
                logger.debug("Could not load operating hours for %s: %s", site_id, exc)
        start, end = self._schedule_bounds(schedule)
        local_dt = current_time.astimezone(SAST) if current_time.tzinfo else current_time.replace(tzinfo=SAST)
        if isinstance(schedule, dict):
            day_schedule = self._day_schedule(schedule, local_dt)
            if day_schedule.get("operational") is False:
                return True
            start = self._parse_time(day_schedule.get("start"), start)
            end = self._parse_time(day_schedule.get("end"), end)
        local_time = local_dt.time()
        if start <= end:
            return not (start <= local_time <= end)
        return end < local_time < start

    async def _canonical_zone_id(self, site_id: str, zone_id: Any) -> str | None:
        raw = str(zone_id or "").strip()
        if not raw:
            return None
        try:
            resolution = await self._zone_resolver.resolve(
                site_id,
                raw,
                source_context="zone_scope_decomposer",
                record_gap=False,
            )
            return resolution.canonical_zone_id or raw
        except Exception:
            return raw

    def _select_writable_point(self, equipment_id: str, points: list[WritablePoint]) -> WritablePoint | None:
        equipment_type = self._equipment_type(equipment_id)
        priorities = {
            "AHU": ("plant_enable", "ahu_on_off", "ahu_mode", "damper_position", "fan_speed_setpoint"),
            "VAV": ("vav_on_off", "damper_position", "vav_flow_setpoint", "zone_temperature_setpoint"),
            "FCU": ("fcu_on_off", "fcu_mode", "temperature_setpoint", "setpoint"),
        }.get(equipment_type, ())
        by_name = {point.point_name: point for point in points}
        for point_name in priorities:
            if point_name in by_name:
                return by_name[point_name]
        return points[0] if points else None

    @staticmethod
    def _target_value_for_point(point_name: str) -> Any:
        point = point_name.lower()
        if point.endswith("_on_off") or point in {"plant_enable", "on_off"}:
            return 0
        if "mode" in point:
            return "off"
        if "temperature_setpoint" in point or point == "setpoint":
            return 26
        return 0

    @staticmethod
    def _action_label(point_name: str, value: Any) -> str:
        if point_name == "plant_enable":
            return "Disable AHU plant enable"
        if "damper" in point_name:
            return f"Set damper to {value}%"
        if "setpoint" in point_name:
            return f"Set back temperature target to {value}"
        if "fan" in point_name:
            return f"Set fan command to {value}"
        return f"Set {point_name} to {value}"

    @staticmethod
    def _unit_for_point(point_name: str) -> str:
        if "damper" in point_name or "fan" in point_name:
            return "%"
        if "temperature" in point_name or point_name == "setpoint":
            return "degC"
        return ""

    @staticmethod
    def _parameter_type_is_writable(parameter_type: str) -> bool:
        text = parameter_type.lower()
        return (
            text in {"command", "setpoint", "writable"}
            or text.startswith(("command:", "setpoint:", "writable:"))
            or any(token in text for token in ("analogoutput", "binaryoutput", "multistateoutput"))
        )

    @staticmethod
    def _equipment_type(equipment_id: str) -> str:
        parts = equipment_id.split("-")
        return parts[1].upper() if len(parts) > 1 else equipment_id.upper()

    @staticmethod
    def _zone_has_high_co2(verdict: Any, state: dict[str, Any]) -> bool:
        state_co2 = ZoneScopeDecomposer._float_or_none(state.get("co2_ppm"))
        if state_co2 is not None:
            return state_co2 >= HIGH_CO2_PROTECT_PPM
        signal = (getattr(verdict, "signals", {}) or {}).get("co2_elevation")
        raw = getattr(signal, "raw_value", None) if signal else None
        if isinstance(raw, dict):
            avg = ZoneScopeDecomposer._float_or_none(raw.get("avg_co2"))
            return avg is not None and avg >= HIGH_CO2_PROTECT_PPM
        return False

    @staticmethod
    def _current_time(current_conditions: dict[str, Any]) -> datetime:
        raw = current_conditions.get("timestamp") or current_conditions.get("current_time")
        if raw:
            try:
                return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            except ValueError:
                pass
        return datetime.now(UTC)

    @staticmethod
    def _schedule_bounds(schedule: Any) -> tuple[time, time]:
        if isinstance(schedule, str) and "-" in schedule:
            start_raw, end_raw = schedule.split("-", 1)
            return ZoneScopeDecomposer._parse_time(start_raw, time(8, 0)), ZoneScopeDecomposer._parse_time(
                end_raw,
                time(18, 0),
            )
        if not isinstance(schedule, dict):
            return time(8, 0), time(18, 0)
        start_raw = schedule.get("start") or schedule.get("open") or "08:00"
        end_raw = schedule.get("end") or schedule.get("close") or "18:00"
        return ZoneScopeDecomposer._parse_time(start_raw, time(8, 0)), ZoneScopeDecomposer._parse_time(
            end_raw,
            time(18, 0),
        )

    @staticmethod
    def _day_schedule(schedule: dict[str, Any], local_dt: datetime) -> dict[str, Any]:
        weekday_key = local_dt.strftime("%A").lower()
        weekend = local_dt.weekday() >= 5
        day_value = schedule.get(weekday_key)
        if isinstance(day_value, dict):
            operational = bool(day_value.get("operational", True))
            return {
                "start": str(day_value.get("start", "00:00" if operational else "08:00")),
                "end": str(day_value.get("end", "23:59" if operational else "18:00")),
                "operational": operational,
            }
        if isinstance(day_value, str):
            return ZoneScopeDecomposer._schedule_from_text(day_value, default_operational=True)

        legacy_value = schedule.get("weekend" if weekend else "weekday")
        if isinstance(legacy_value, str):
            return ZoneScopeDecomposer._schedule_from_text(legacy_value, default_operational=True)

        if "start" in schedule or "end" in schedule:
            return {
                "start": str(schedule.get("start", "08:00")),
                "end": str(schedule.get("end", "18:00")),
                "operational": bool(schedule.get("operational", not weekend)),
            }
        return {"start": "08:00", "end": "18:00", "operational": not weekend}

    @staticmethod
    def _schedule_from_text(value: str, *, default_operational: bool) -> dict[str, Any]:
        text = value.strip()
        if text.lower() in {"closed", "false", "off"}:
            return {"start": "08:00", "end": "18:00", "operational": False}
        if "-" in text:
            start_text, end_text = text.split("-", 1)
            return {"start": start_text.strip(), "end": end_text.strip(), "operational": True}
        return {"start": "08:00", "end": "18:00", "operational": default_operational}

    @staticmethod
    def _parse_time(value: Any, fallback: time) -> time:
        try:
            hour, minute = str(value).split(":", 1)
            return time(int(hour), int(minute[:2]))
        except (ValueError, TypeError):
            return fallback

    @staticmethod
    def _is_stale(value: Any, *, minutes: int = ZONE_SCOPE_STATE_FRESHNESS_MINUTES) -> bool:
        if not value:
            return True
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            return datetime.now(UTC) - parsed.astimezone(UTC) > timedelta(minutes=minutes)
        except ValueError:
            return True

    @staticmethod
    def _float_or_none(value: Any) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _int_or_none(value: Any) -> int | None:
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None

    def _client(self) -> Any:
        if self._sb is None:
            from app.database.supabase_client import get_supabase_client

            self._sb = get_supabase_client()
        return self._sb


_zone_scope_decomposer: ZoneScopeDecomposer | None = None


def get_zone_scope_decomposer() -> ZoneScopeDecomposer:
    global _zone_scope_decomposer
    if _zone_scope_decomposer is None:
        _zone_scope_decomposer = ZoneScopeDecomposer()
    return _zone_scope_decomposer
