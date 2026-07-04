"""Deterministic zone/system reflex reconciliation.

This service evaluates current state on a fixed cadence. It does not call the
LLM optimizer and does not replay discrete occupancy events. Zone occupancy
events are useful as an event surface, but the reflex check itself is a simple
current-state scan so scheduler cadence and trigger cooldown cannot fight.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

from app.models.recommendation import ActionRiskLevel, Recommendation, RecommendationStatus
from app.services.zone_identity_resolver import ZoneIdentityResolver, get_zone_identity_resolver

logger = logging.getLogger("sentinel.reflex_reconciliation")

SAST = timezone(timedelta(hours=2))
RECURRENCE_LOOKBACK_DAYS = 35
RECURRENCE_THRESHOLD = 3
BUCKET_HOURS = 2
LIGHTING_TELEMETRY_FRESHNESS_MINUTES = 60
ZONE_RELEVANT_EQUIPMENT_TYPES = {
    "ahu",
    "fcu",
    "vav",
    "dali",
    "lighting_driver",
    "lighting_panel",
    "luminaire",
}

POINT_IN_TIME_REFLEX_ACTION_TYPES = {
    "operational_mismatch",
    "comfort_risk",
}


@dataclass
class ZoneSystemState:
    site_id: str
    source_zone_id: str
    canonical_zone_id: str
    system_type: str
    occupancy_pct: float | None = None
    occupied: bool | None = None
    running: bool | None = None
    room_temp_c: float | None = None
    setpoint_c: float | None = None
    total_watts: float | None = None
    active_luminaires: int | None = None
    avg_dim_level: float | None = None
    source: str = "unknown"
    equipment: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ReflexFinding:
    site_id: str
    canonical_zone_id: str
    source_zone_id: str
    system_type: str
    rule_key: str
    category: str
    severity: str
    reason: str
    evidence: dict[str, Any] = field(default_factory=dict)


class ReflexRule:
    system_type = "generic"
    rule_key = "generic"

    def evaluate(self, state: ZoneSystemState, *, now: datetime) -> ReflexFinding | None:
        raise NotImplementedError


class EmptyZoneHvacRunningRule(ReflexRule):
    system_type = "hvac"
    rule_key = "hvac.empty_zone_running"

    def __init__(self, empty_threshold_pct: float = 5.0):
        self.empty_threshold_pct = empty_threshold_pct

    def evaluate(self, state: ZoneSystemState, *, now: datetime) -> ReflexFinding | None:
        if state.system_type != self.system_type or state.running is not True:
            return None
        occupancy = state.occupancy_pct
        if occupancy is None or occupancy > self.empty_threshold_pct:
            return None
        return ReflexFinding(
            site_id=state.site_id,
            canonical_zone_id=state.canonical_zone_id,
            source_zone_id=state.source_zone_id,
            system_type=self.system_type,
            rule_key=self.rule_key,
            category="operational_mismatch",
            severity="medium",
            reason=(
                f"Zone {state.source_zone_id} is empty/near-empty ({occupancy:.1f}% occupancy) "
                "while local HVAC is still running."
            ),
            evidence=_state_evidence(state),
        )


class OccupiedZoneHvacIdleComfortRiskRule(ReflexRule):
    system_type = "hvac"
    rule_key = "hvac.occupied_zone_idle_comfort_risk"

    def __init__(self, occupied_threshold_pct: float = 10.0, min_temp_c: float = 20.0, max_temp_c: float = 26.0):
        self.occupied_threshold_pct = occupied_threshold_pct
        self.min_temp_c = min_temp_c
        self.max_temp_c = max_temp_c

    def evaluate(self, state: ZoneSystemState, *, now: datetime) -> ReflexFinding | None:
        if state.system_type != self.system_type or state.running is not False:
            return None
        if state.occupancy_pct is None or state.occupancy_pct < self.occupied_threshold_pct:
            return None
        if state.room_temp_c is None or self.min_temp_c <= state.room_temp_c <= self.max_temp_c:
            return None
        return ReflexFinding(
            site_id=state.site_id,
            canonical_zone_id=state.canonical_zone_id,
            source_zone_id=state.source_zone_id,
            system_type=self.system_type,
            rule_key=self.rule_key,
            category="comfort_risk",
            severity="high",
            reason=(
                f"Zone {state.source_zone_id} is occupied ({state.occupancy_pct:.1f}%) and at "
                f"{state.room_temp_c:.1f}C while local HVAC appears idle."
            ),
            evidence=_state_evidence(state),
        )


class EmptyZoneLightsOnRule(ReflexRule):
    system_type = "lighting"
    rule_key = "lighting.empty_zone_lights_on"

    def __init__(self, empty_threshold_pct: float = 5.0, watt_threshold: float = 20.0, dim_threshold: float = 5.0):
        self.empty_threshold_pct = empty_threshold_pct
        self.watt_threshold = watt_threshold
        self.dim_threshold = dim_threshold

    def evaluate(self, state: ZoneSystemState, *, now: datetime) -> ReflexFinding | None:
        if state.system_type != self.system_type:
            return None
        if (
            not _has_lighting_telemetry(state)
            or state.occupancy_pct is None
            or state.occupancy_pct > self.empty_threshold_pct
        ):
            return None
        if not _lighting_is_on(state, watt_threshold=self.watt_threshold, dim_threshold=self.dim_threshold):
            return None
        return ReflexFinding(
            site_id=state.site_id,
            canonical_zone_id=state.canonical_zone_id,
            source_zone_id=state.source_zone_id,
            system_type=self.system_type,
            rule_key=self.rule_key,
            category="operational_mismatch",
            severity="medium",
            reason=(
                f"Zone {state.source_zone_id} is empty/near-empty ({state.occupancy_pct:.1f}% occupancy) "
                "while lighting energy telemetry shows lights are on."
            ),
            evidence=_state_evidence(state),
        )


class OccupiedZoneLightsOffRule(ReflexRule):
    system_type = "lighting"
    rule_key = "lighting.occupied_zone_lights_off"

    def __init__(self, occupied_threshold_pct: float = 10.0):
        self.occupied_threshold_pct = occupied_threshold_pct

    def evaluate(self, state: ZoneSystemState, *, now: datetime) -> ReflexFinding | None:
        if state.system_type != self.system_type:
            return None
        if (
            not _has_lighting_telemetry(state)
            or state.occupancy_pct is None
            or state.occupancy_pct < self.occupied_threshold_pct
        ):
            return None
        if _lighting_is_on(state):
            return None
        return ReflexFinding(
            site_id=state.site_id,
            canonical_zone_id=state.canonical_zone_id,
            source_zone_id=state.source_zone_id,
            system_type=self.system_type,
            rule_key=self.rule_key,
            category="comfort_risk",
            severity="medium",
            reason=(
                f"Zone {state.source_zone_id} is occupied ({state.occupancy_pct:.1f}%) but lighting telemetry "
                "shows lights are off or near-zero."
            ),
            evidence=_state_evidence(state),
        )


class ReflexReconciliationRepository:
    """DB access for reflex reconciliation current-state scans."""

    async def list_site_ids(self) -> list[str]:
        from app.core.site_resolver import get_registered_site_ids

        return list(get_registered_site_ids())

    async def get_site_uuid(self, site_id: str) -> str | None:
        from app.database.supabase_client import get_async_supabase_client

        client = await get_async_supabase_client()
        result = await client.table("sites").select("id").eq("code", site_id).limit(1).execute()
        if result.data:
            return str(result.data[0].get("id"))
        return None

    async def list_latest_fcu_zone_state(self, site_id: str) -> list[dict[str, Any]]:
        from app.database.supabase_client import get_async_supabase_client

        client = await get_async_supabase_client()
        result = (
            await client.table("fcu_zone_state")
            .select("zone_id,occupancy_pct,room_temp_c,setpoint_c,fcu_inferred_running,occupancy_source,timestamp")
            .eq("site_id", site_id)
            .order("timestamp", desc=True)
            .limit(500)
            .execute()
        )
        latest: dict[str, dict[str, Any]] = {}
        for row in result.data or []:
            zone_id = str(row.get("zone_id") or "")
            if zone_id and zone_id not in latest:
                latest[zone_id] = row
        return list(latest.values())

    async def list_latest_lighting_energy(self, site_id: str) -> list[dict[str, Any]]:
        from app.database.supabase_client import get_async_supabase_client

        client = await get_async_supabase_client()
        since = (datetime.now(UTC) - timedelta(minutes=LIGHTING_TELEMETRY_FRESHNESS_MINUTES)).isoformat()
        result = (
            await client.table("lighting_energy")
            .select("zone_id,controller_id,total_watts,active_luminaires,avg_dim_level,time")
            .eq("site_id", site_id)
            .gte("time", since)
            .order("time", desc=True)
            .limit(500)
            .execute()
        )
        latest: dict[str, dict[str, Any]] = {}
        for row in result.data or []:
            zone_id = str(row.get("zone_id") or "")
            if zone_id and zone_id not in latest:
                latest[zone_id] = row
        return list(latest.values())

    async def list_equipment_by_zone(self, site_id: str) -> dict[str, list[dict[str, Any]]]:
        from app.database.supabase_client import get_async_supabase_client

        site_uuid = await self.get_site_uuid(site_id)
        if not site_uuid:
            return {}
        client = await get_async_supabase_client()
        result = await client.table("equipment").select("code,type,zone_key,status").eq("site_id", site_uuid).execute()
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in result.data or []:
            zone_key = str(row.get("zone_key") or "").strip()
            if zone_key:
                grouped.setdefault(zone_key, []).append(row)
            elif _is_zone_relevant_equipment(row):
                await self.record_equipment_zone_gap(
                    site_id=site_id,
                    equipment_code=str(row.get("code") or "unknown"),
                    equipment_type=str(row.get("type") or "unknown"),
                    status=str(row.get("status") or "unknown"),
                    reason="equipment_missing_zone_key",
                )
        return grouped

    async def record_equipment_zone_gap(
        self,
        *,
        site_id: str,
        equipment_code: str,
        equipment_type: str,
        status: str,
        reason: str,
    ) -> None:
        from app.database.supabase_client import get_async_supabase_client

        client = await get_async_supabase_client()
        since = (datetime.now(UTC) - timedelta(hours=24)).isoformat()
        existing = (
            await client.table("reflex_zone_resolution_gaps")
            .select("id")
            .eq("site_id", site_id)
            .eq("source_zone_id", equipment_code)
            .eq("source_context", "equipment.zone_key")
            .eq("reason", reason)
            .gte("observed_at", since)
            .limit(1)
            .execute()
        )
        if existing.data:
            return

        await (
            client.table("reflex_zone_resolution_gaps")
            .insert(
                {
                    "site_id": site_id,
                    "source_zone_id": equipment_code,
                    "source_context": "equipment.zone_key",
                    "reason": reason,
                    "observed_at": datetime.now(UTC).isoformat(),
                    "metadata": {
                        "equipment_code": equipment_code,
                        "equipment_type": equipment_type,
                        "status": status,
                        "coverage_gap": "equipment_not_attached_to_canonical_zone",
                    },
                }
            )
            .execute()
        )

    async def record_occurrence(self, finding: ReflexFinding, *, now: datetime) -> int:
        from app.database.supabase_client import get_async_supabase_client

        client = await get_async_supabase_client()
        day_of_week, bucket, local_date = recurrence_bucket_parts(now)
        existing_bucket = (
            await client.table("reflex_reconciliation_occurrences")
            .select("id")
            .eq("site_id", finding.site_id)
            .eq("canonical_zone_id", finding.canonical_zone_id)
            .eq("system_type", finding.system_type)
            .eq("rule_key", finding.rule_key)
            .eq("local_date", local_date)
            .eq("local_time_bucket", bucket)
            .limit(1)
            .execute()
        )
        if not existing_bucket.data:
            await (
                client.table("reflex_reconciliation_occurrences")
                .insert(
                    {
                        "site_id": finding.site_id,
                        "canonical_zone_id": finding.canonical_zone_id,
                        "source_zone_id": finding.source_zone_id,
                        "system_type": finding.system_type,
                        "rule_key": finding.rule_key,
                        "severity": finding.severity,
                        "occurred_at": now.isoformat(),
                        "local_day_of_week": day_of_week,
                        "local_time_bucket": bucket,
                        "local_date": local_date,
                        "finding_payload": {
                            "category": finding.category,
                            "reason": finding.reason,
                            "evidence": finding.evidence,
                        },
                    }
                )
                .execute()
            )

        since = (now - timedelta(days=RECURRENCE_LOOKBACK_DAYS)).isoformat()
        result = (
            await client.table("reflex_reconciliation_occurrences")
            .select("local_date")
            .eq("site_id", finding.site_id)
            .eq("canonical_zone_id", finding.canonical_zone_id)
            .eq("system_type", finding.system_type)
            .eq("rule_key", finding.rule_key)
            .eq("local_day_of_week", day_of_week)
            .eq("local_time_bucket", bucket)
            .gte("occurred_at", since)
            .limit(1000)
            .execute()
        )
        return len({str(row.get("local_date")) for row in result.data or [] if row.get("local_date")})

    async def list_active_reflex_recommendations(self, site_id: str) -> list[dict[str, Any]]:
        from app.database.supabase_client import get_async_supabase_client

        client = await get_async_supabase_client()
        result = (
            await client.table("recommendations")
            .select("*")
            .eq("site_id", site_id)
            .eq("source", "reflex_reconciliation")
            .in_("status", ["pending", "advisory_info"])
            .order("timestamp", desc=True)
            .limit(1000)
            .execute()
        )
        return result.data or []

    async def update_recommendation_observation(
        self,
        recommendation: dict[str, Any],
        finding: ReflexFinding,
        *,
        action_type: str,
        now: datetime,
    ) -> Recommendation | None:
        from app.database.supabase_client import get_async_supabase_client

        client = await get_async_supabase_client()
        metadata = dict(recommendation.get("metadata") or {})
        observation_count = _int_or_none(metadata.get("observation_count")) or 1
        timestamp = recommendation.get("timestamp")
        metadata.update(
            {
                "canonical_zone_id": finding.canonical_zone_id,
                "source_zone_id": finding.source_zone_id,
                "system_type": finding.system_type,
                "rule_key": finding.rule_key,
                "evidence": finding.evidence,
                "first_observed_at": metadata.get("first_observed_at") or timestamp or now.isoformat(),
                "last_observed_at": now.isoformat(),
                "observation_count": observation_count + 1,
                "schedule_write_available": False,
            }
        )
        payload = {
            "timestamp": now.replace(tzinfo=None).isoformat(),
            "risk_level": ActionRiskLevel.HIGH.value if finding.severity == "high" else ActionRiskLevel.MEDIUM.value,
            "reason": finding.reason,
            "expected_impact": {"category": finding.category, "manual_action_required": True},
            "metadata": metadata,
        }
        result = await client.table("recommendations").update(payload).eq("id", recommendation["id"]).execute()
        if result.data:
            return Recommendation.from_dict(result.data[0])
        return None

    async def resolve_recommendations(
        self,
        recommendations: list[dict[str, Any]],
        *,
        now: datetime,
        reason: str,
    ) -> int:
        from app.database.supabase_client import get_async_supabase_client

        client = await get_async_supabase_client()
        resolved = 0
        for row in recommendations:
            metadata = dict(row.get("metadata") or {})
            metadata.update(
                {
                    "resolved_at": now.isoformat(),
                    "resolution_reason": reason,
                    "last_observed_at": metadata.get("last_observed_at") or row.get("timestamp"),
                }
            )
            result = (
                await client.table("recommendations")
                .update({"status": RecommendationStatus.EXPIRED.value, "metadata": metadata})
                .eq("id", row["id"])
                .execute()
            )
            resolved += len(result.data or [])
        return resolved

    async def expire_point_in_time_for_finding(self, finding: ReflexFinding, *, now: datetime, reason: str) -> int:
        active = await self.list_active_reflex_recommendations(finding.site_id)
        rows = [
            row
            for row in active
            if str(row.get("action_type") or "") in POINT_IN_TIME_REFLEX_ACTION_TYPES
            and _reflex_row_key(row)
            == _reflex_key(
                site_id=finding.site_id,
                canonical_zone_id=finding.canonical_zone_id,
                system_type=finding.system_type,
                rule_key=finding.rule_key,
                action_type=finding.category,
            )
        ]
        return await self.resolve_recommendations(rows, now=now, reason=reason)

    async def open_schedule_defect_exists(self, finding: ReflexFinding) -> bool:
        from app.database.supabase_client import get_async_supabase_client

        client = await get_async_supabase_client()
        result = (
            await client.table("recommendations")
            .select("id")
            .eq("site_id", finding.site_id)
            .eq("action_type", "schedule_defect")
            .eq("target_equipment", finding.canonical_zone_id)
            .in_("status", ["pending", "advisory_info"])
            .limit(1)
            .execute()
        )
        return any(
            _reflex_row_key(row)
            == _reflex_key(
                site_id=finding.site_id,
                canonical_zone_id=finding.canonical_zone_id,
                system_type=finding.system_type,
                rule_key=finding.rule_key,
                action_type="schedule_defect",
            )
            for row in result.data or []
        )

    async def create_recommendation(self, finding: ReflexFinding, *, action_type: str, now: datetime) -> Recommendation:
        from app.database.repositories.recommendation_repository import get_recommendation_repository

        status = RecommendationStatus.ADVISORY_INFO
        risk = ActionRiskLevel.HIGH if finding.severity == "high" else ActionRiskLevel.MEDIUM
        reason = finding.reason
        if action_type == "schedule_defect":
            reason = (
                f"Recurring {finding.system_type} operating mismatch detected for {finding.canonical_zone_id}. "
                "Likely BMS timer/schedule defect; manual BMS schedule correction is required. "
                f"Latest evidence: {finding.reason}"
            )

        rec = Recommendation(
            site_id=finding.site_id,
            timestamp=now.replace(tzinfo=None),
            action_type=action_type,
            risk_level=risk,
            target_equipment=finding.canonical_zone_id,
            action={
                "type": "manual_schedule_review" if action_type == "schedule_defect" else "manual_operator_review",
                "system_type": finding.system_type,
                "rule_key": finding.rule_key,
                "auto_actionable": False,
            },
            reason=reason,
            expected_impact={"category": finding.category, "manual_action_required": True},
            confidence="high",
            confidence_score=0.85,
            profile="reflex_reconciliation",
            status=status,
            requires_approval=False,
            source="reflex_reconciliation",
            source_type="deterministic_rule",
            shadow_mode=False,
            metadata={
                "canonical_zone_id": finding.canonical_zone_id,
                "source_zone_id": finding.source_zone_id,
                "system_type": finding.system_type,
                "rule_key": finding.rule_key,
                "evidence": finding.evidence,
                "first_observed_at": now.isoformat(),
                "last_observed_at": now.isoformat(),
                "observation_count": 1,
                "schedule_write_available": False,
            },
        )
        return await get_recommendation_repository().create(rec)


class ReflexNotificationSink:
    """Manager notification for first schedule-defect creation."""

    async def notify_schedule_defect(self, rec: Recommendation, finding: ReflexFinding) -> bool:
        try:
            from app.config.settings import settings
            from app.services.telegram_message_sender import TelegramMessageSender

            bot_token = getattr(settings, "sentry_manager_bot_token", None) or getattr(
                settings, "telegram_bot_token", None
            )
            chat_id = getattr(settings, "telegram_alert_chat_id", None) or getattr(settings, "sentry_fm_chat_id", None)
            if not bot_token or not chat_id:
                logger.warning("[REFLEX] Schedule defect notification skipped: missing manager bot token/chat id")
                return False

            text = (
                "SENTINEL Schedule Defect\n"
                f"Site: {finding.site_id}\n"
                f"Zone: {finding.canonical_zone_id}\n"
                f"System: {finding.system_type}\n"
                f"Issue: {finding.reason}\n\n"
                "This looks recurring, so it likely needs BMS schedule/timer correction. "
                "SENTINEL cannot write schedules on this bridge yet; this is advisory/manual-only."
            )
            result = await TelegramMessageSender(bot_token).send_text(str(chat_id), text, parse_mode=None)
            return bool(result.get("ok"))
        except Exception as exc:
            logger.warning("[REFLEX] Schedule defect notification failed: %s", exc)
            return False


class ReflexReconciliationService:
    """Evaluate current zone/system state and persist reflex findings."""

    def __init__(
        self,
        *,
        repository: ReflexReconciliationRepository | None = None,
        resolver: ZoneIdentityResolver | None = None,
        notifier: ReflexNotificationSink | None = None,
        rules: list[ReflexRule] | None = None,
    ):
        self.repository = repository or ReflexReconciliationRepository()
        self.resolver = resolver or get_zone_identity_resolver()
        self.notifier = notifier or ReflexNotificationSink()
        self.rules = rules or [
            EmptyZoneHvacRunningRule(),
            OccupiedZoneHvacIdleComfortRiskRule(),
            EmptyZoneLightsOnRule(),
            OccupiedZoneLightsOffRule(),
        ]

    async def reconcile_site(self, site_id: str, *, now: datetime | None = None) -> list[Recommendation]:
        now = _ensure_aware(now or datetime.now(UTC))
        states = await self._load_current_states(site_id)
        active_rows = await self.repository.list_active_reflex_recommendations(site_id)
        active_by_key, duplicate_rows = _active_reflex_rows_by_key(active_rows)
        if duplicate_rows:
            await self.repository.resolve_recommendations(
                duplicate_rows,
                now=now,
                reason="superseded_by_reflex_state_dedup",
            )

        evaluated_rule_keys: set[tuple[str, str, str, str]] = set()
        observed_finding_keys: set[tuple[str, str, str, str, str]] = set()
        created: list[Recommendation] = []
        for state in states:
            for rule in self._rules_for_system(state.system_type):
                evaluated_rule_keys.add(
                    _rule_eval_key(
                        site_id=site_id,
                        canonical_zone_id=state.canonical_zone_id,
                        system_type=state.system_type,
                        rule_key=rule.rule_key,
                    )
                )
                finding = rule.evaluate(state, now=now)
                if not finding:
                    continue
                rec = await self._upsert_finding(finding, active_by_key=active_by_key, now=now)
                observed_finding_keys.add(
                    _reflex_key(
                        site_id=finding.site_id,
                        canonical_zone_id=finding.canonical_zone_id,
                        system_type=finding.system_type,
                        rule_key=finding.rule_key,
                        action_type=finding.category,
                    )
                )
                if rec:
                    created.append(rec)

        resolved_rows = _resolved_point_in_time_rows(
            active_rows,
            evaluated_rule_keys=evaluated_rule_keys,
            observed_finding_keys=observed_finding_keys,
        )
        if resolved_rows:
            await self.repository.resolve_recommendations(
                resolved_rows,
                now=now,
                reason="condition_cleared",
            )
        return created

    async def reconcile_all_sites(self, *, now: datetime | None = None) -> dict[str, int]:
        site_ids = await self.repository.list_site_ids()
        counts: dict[str, int] = {}
        for site_id in site_ids:
            try:
                counts[site_id] = len(await self.reconcile_site(site_id, now=now))
            except Exception as exc:
                logger.warning("[REFLEX] Reconciliation failed for %s: %s", site_id, exc)
        return counts

    async def _load_current_states(self, site_id: str) -> list[ZoneSystemState]:
        equipment_by_zone = await self.repository.list_equipment_by_zone(site_id)
        occupancy_by_canonical: dict[str, dict[str, Any]] = {}
        states: list[ZoneSystemState] = []

        for row in await self.repository.list_latest_fcu_zone_state(site_id):
            source_zone_id = str(row.get("zone_id") or "")
            resolution = await self.resolver.resolve(site_id, source_zone_id, source_context="fcu_zone_state")
            if not resolution.resolved:
                continue
            canonical = str(resolution.canonical_zone_id)
            occupancy_by_canonical[canonical] = row
            occupancy_pct = _float_or_none(row.get("occupancy_pct"))
            states.append(
                ZoneSystemState(
                    site_id=site_id,
                    source_zone_id=source_zone_id,
                    canonical_zone_id=canonical,
                    system_type="hvac",
                    occupancy_pct=occupancy_pct,
                    occupied=occupancy_pct is not None and occupancy_pct > 5.0,
                    # NULL means "running state unknowable from telemetry" — must not
                    # collapse to False or the occupied-zone-idle rule fires on noise.
                    running=(
                        bool(row["fcu_inferred_running"]) if row.get("fcu_inferred_running") is not None else None
                    ),
                    room_temp_c=_float_or_none(row.get("room_temp_c")),
                    setpoint_c=_float_or_none(row.get("setpoint_c")),
                    source=str(row.get("occupancy_source") or "fcu_zone_state"),
                    equipment=equipment_by_zone.get(canonical, []),
                )
            )

        for row in await self.repository.list_latest_lighting_energy(site_id):
            source_zone_id = str(row.get("zone_id") or "")
            resolution = await self.resolver.resolve(site_id, source_zone_id, source_context="lighting_energy")
            if not resolution.resolved:
                continue
            canonical = str(resolution.canonical_zone_id)
            occupancy_row = occupancy_by_canonical.get(canonical, {})
            occupancy_pct = _float_or_none(occupancy_row.get("occupancy_pct"))
            states.append(
                ZoneSystemState(
                    site_id=site_id,
                    source_zone_id=source_zone_id,
                    canonical_zone_id=canonical,
                    system_type="lighting",
                    occupancy_pct=occupancy_pct,
                    occupied=occupancy_pct is not None and occupancy_pct > 5.0,
                    total_watts=_float_or_none(row.get("total_watts")),
                    active_luminaires=_int_or_none(row.get("active_luminaires")),
                    avg_dim_level=_float_or_none(row.get("avg_dim_level")),
                    source="lighting_energy",
                    equipment=equipment_by_zone.get(canonical, []),
                )
            )
        return states

    def _rules_for_system(self, system_type: str) -> list[ReflexRule]:
        return [rule for rule in self.rules if rule.system_type == system_type]

    async def _upsert_finding(
        self,
        finding: ReflexFinding,
        *,
        active_by_key: dict[tuple[str, str, str, str, str], dict[str, Any]],
        now: datetime,
    ) -> Recommendation | None:
        key = _reflex_key(
            site_id=finding.site_id,
            canonical_zone_id=finding.canonical_zone_id,
            system_type=finding.system_type,
            rule_key=finding.rule_key,
            action_type=finding.category,
        )
        if key in active_by_key:
            await self.repository.update_recommendation_observation(
                active_by_key[key],
                finding,
                action_type=finding.category,
                now=now,
            )
            return None

        occurrence_count = await self.repository.record_occurrence(finding, now=now)
        if occurrence_count >= RECURRENCE_THRESHOLD:
            return await self._create_schedule_defect_if_needed(finding, now=now)
        return await self.repository.create_recommendation(finding, action_type=finding.category, now=now)

    async def _create_schedule_defect_if_needed(
        self, finding: ReflexFinding, *, now: datetime
    ) -> Recommendation | None:
        if await self.repository.open_schedule_defect_exists(finding):
            await self.repository.expire_point_in_time_for_finding(
                finding,
                now=now,
                reason="superseded_by_schedule_defect",
            )
            return None
        rec = await self.repository.create_recommendation(finding, action_type="schedule_defect", now=now)
        await self.repository.expire_point_in_time_for_finding(
            finding,
            now=now,
            reason="superseded_by_schedule_defect",
        )
        await self.notifier.notify_schedule_defect(rec, finding)
        return rec


def _reflex_key(
    *,
    site_id: str,
    canonical_zone_id: str,
    system_type: str,
    rule_key: str,
    action_type: str,
) -> tuple[str, str, str, str, str]:
    return (site_id, canonical_zone_id, system_type, rule_key, action_type)


def _rule_eval_key(
    *,
    site_id: str,
    canonical_zone_id: str,
    system_type: str,
    rule_key: str,
) -> tuple[str, str, str, str]:
    return (site_id, canonical_zone_id, system_type, rule_key)


def _reflex_row_key(row: dict[str, Any]) -> tuple[str, str, str, str, str] | None:
    metadata = row.get("metadata") or {}
    action = row.get("action") or {}
    if not isinstance(metadata, dict):
        metadata = {}
    if not isinstance(action, dict):
        action = {}

    site_id = str(row.get("site_id") or "")
    canonical_zone_id = str(metadata.get("canonical_zone_id") or row.get("target_equipment") or "")
    system_type = str(metadata.get("system_type") or action.get("system_type") or "")
    rule_key = str(metadata.get("rule_key") or action.get("rule_key") or "")
    action_type = str(row.get("action_type") or "")
    if not site_id or not canonical_zone_id or not system_type or not rule_key or not action_type:
        return None
    return _reflex_key(
        site_id=site_id,
        canonical_zone_id=canonical_zone_id,
        system_type=system_type,
        rule_key=rule_key,
        action_type=action_type,
    )


def _active_reflex_rows_by_key(
    rows: list[dict[str, Any]],
) -> tuple[dict[tuple[str, str, str, str, str], dict[str, Any]], list[dict[str, Any]]]:
    grouped: dict[tuple[str, str, str, str, str], list[dict[str, Any]]] = {}
    for row in rows:
        action_type = str(row.get("action_type") or "")
        if action_type not in POINT_IN_TIME_REFLEX_ACTION_TYPES:
            continue
        key = _reflex_row_key(row)
        if key:
            grouped.setdefault(key, []).append(row)

    active_by_key: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
    duplicate_rows: list[dict[str, Any]] = []
    for key, keyed_rows in grouped.items():
        sorted_rows = sorted(keyed_rows, key=lambda item: str(item.get("timestamp") or ""), reverse=True)
        active_by_key[key] = sorted_rows[0]
        duplicate_rows.extend(sorted_rows[1:])
    return active_by_key, duplicate_rows


def _resolved_point_in_time_rows(
    rows: list[dict[str, Any]],
    *,
    evaluated_rule_keys: set[tuple[str, str, str, str]],
    observed_finding_keys: set[tuple[str, str, str, str, str]],
) -> list[dict[str, Any]]:
    resolved: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for row in rows:
        action_type = str(row.get("action_type") or "")
        if action_type not in POINT_IN_TIME_REFLEX_ACTION_TYPES:
            continue
        key = _reflex_row_key(row)
        if not key:
            continue
        eval_key = key[:4]
        row_id = str(row.get("id") or "")
        if eval_key in evaluated_rule_keys and key not in observed_finding_keys and row_id not in seen_ids:
            resolved.append(row)
            seen_ids.add(row_id)
    return resolved


def recurrence_bucket(now: datetime) -> tuple[int, str]:
    day_of_week, bucket, _local_date = recurrence_bucket_parts(now)
    return day_of_week, bucket


def recurrence_bucket_parts(now: datetime) -> tuple[int, str, str]:
    local = _ensure_aware(now).astimezone(SAST)
    start_hour = (local.hour // BUCKET_HOURS) * BUCKET_HOURS
    end_hour = (start_hour + BUCKET_HOURS) % 24
    return local.weekday(), f"{start_hour:02d}:00-{end_hour:02d}:00", local.date().isoformat()


def _ensure_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _has_lighting_telemetry(state: ZoneSystemState) -> bool:
    return state.total_watts is not None or state.active_luminaires is not None or state.avg_dim_level is not None


def _lighting_is_on(state: ZoneSystemState, *, watt_threshold: float = 20.0, dim_threshold: float = 5.0) -> bool:
    if state.active_luminaires is not None and state.active_luminaires > 0:
        return True
    if state.total_watts is not None and state.total_watts > watt_threshold:
        return True
    if state.avg_dim_level is not None and state.avg_dim_level > dim_threshold:
        return True
    return False


def _state_evidence(state: ZoneSystemState) -> dict[str, Any]:
    return {
        "source_zone_id": state.source_zone_id,
        "canonical_zone_id": state.canonical_zone_id,
        "system_type": state.system_type,
        "occupancy_pct": state.occupancy_pct,
        "running": state.running,
        "room_temp_c": state.room_temp_c,
        "setpoint_c": state.setpoint_c,
        "total_watts": state.total_watts,
        "active_luminaires": state.active_luminaires,
        "avg_dim_level": state.avg_dim_level,
        "source": state.source,
        "equipment": [
            {"code": item.get("code"), "type": item.get("type"), "status": item.get("status")}
            for item in state.equipment
        ],
    }


def _float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _is_zone_relevant_equipment(row: dict[str, Any]) -> bool:
    equipment_type = str(row.get("type") or "").strip().lower()
    status = str(row.get("status") or "").strip().lower()
    if status == "offline":
        return False
    return equipment_type in ZONE_RELEVANT_EQUIPMENT_TYPES


_service: ReflexReconciliationService | None = None


def get_reflex_reconciliation_service() -> ReflexReconciliationService:
    global _service
    if _service is None:
        _service = ReflexReconciliationService()
    return _service
