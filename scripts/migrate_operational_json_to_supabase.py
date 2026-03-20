#!/usr/bin/env python3
"""Backfill JSON-backed operational SENTINEL data into local Supabase/Postgres.

This is a one-shot migration helper for operational JSON domains that should
be canonical in Postgres.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from pathlib import Path
from typing import Any

import psycopg2
from psycopg2.extras import Json
from psycopg2 import errors


REPO_ROOT = Path(__file__).resolve().parents[1]
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@127.0.0.1:55322/postgres",
)

AGENT_MEMORY_FILE = REPO_ROOT / "backend" / "app" / "data" / "agent_memory.json"
USER_ENTITLEMENTS_FILE = REPO_ROOT / "backend" / "app" / "data" / "user_entitlements.json"
DECISION_RECORDS_FILE = REPO_ROOT / "backend" / "app" / "data" / "decision_memory" / "decision_records.json"
DECISION_PATTERNS_FILE = REPO_ROOT / "backend" / "app" / "data" / "decision_memory" / "decision_patterns.json"
RECOMMENDATIONS_FILE = REPO_ROOT / "backend" / "app" / "data" / "recommendations.json"
NOTIFICATION_PREFS_FILE = REPO_ROOT / "backend" / "app" / "database" / "data" / "notification_preferences.json"
NOTIFICATION_DELIVERY_FILE = REPO_ROOT / "backend" / "app" / "database" / "data" / "notification_delivery_log.json"
SPACE_OCCUPANCY_FILE = REPO_ROOT / "backend" / "app" / "data" / "space" / "occupancy_events.json"
SPACE_GHOST_FILE = REPO_ROOT / "backend" / "app" / "data" / "space" / "ghost_findings.json"
SPACE_CURRENT_STATE_FILE = REPO_ROOT / "backend" / "app" / "data" / "space" / "room_current_state.json"
SPACE_ROOM_EVENTS_FILE = REPO_ROOT / "backend" / "app" / "data" / "space" / "room_events.json"
SPACE_RIGHTSIZING_FILE = REPO_ROOT / "backend" / "app" / "data" / "space" / "rightsizing_findings.json"
SPACE_FOCUS_SESSIONS_FILE = REPO_ROOT / "backend" / "app" / "data" / "space" / "focus_room_sessions.json"
SPACE_CONCIERGES_FILE = REPO_ROOT / "backend" / "app" / "data" / "space" / "concierges.json"
SPACE_ROOM_REGISTRY_FILE = REPO_ROOT / "backend" / "app" / "data" / "space" / "room_registry.json"
SPACE_SENSOR_DEVICES_FILE = REPO_ROOT / "backend" / "app" / "data" / "space" / "sensor_devices.json"
SPACE_SITE_STRUCTURE_FILE = REPO_ROOT / "backend" / "app" / "data" / "space" / "site_structure.json"
SPACE_SETTINGS_FILE = REPO_ROOT / "backend" / "app" / "data" / "space" / "space_settings.json"
CAPEX_ANALYSES_FILE = REPO_ROOT / "backend" / "app" / "data" / "capex_analyses.json"
USERS_FILE = REPO_ROOT / "backend" / "app" / "data" / "users.json"

DEFAULT_SPACE_SETTINGS = {
    "ghost_booking_grace_minutes": 5,
    "concierge_response_window_minutes": 15,
    "sensor_silence_threshold_minutes": 30,
    "right_sizing_grace_minutes": 20,
    "early_vacate_threshold_minutes": 90,
    "sporadic_use_threshold_pct": 25,
    "brief_occupation_threshold_min": 30,
}

SQL_MIGRATIONS = [
    REPO_ROOT / "backend" / "supabase" / "migrations" / "20260227_001_agent_memory.sql",
    REPO_ROOT / "backend" / "supabase" / "migrations" / "20260218_001_technician_notification_channels.sql",
    REPO_ROOT / "backend" / "supabase" / "migrations" / "20260218_002_technician_notification_preferences.sql",
    REPO_ROOT / "backend" / "supabase" / "migrations" / "20260218_003_notification_delivery_log.sql",
    REPO_ROOT / "backend" / "supabase" / "migrations" / "20260222_001_system_notifier_technician.sql",
    REPO_ROOT / "supabase" / "migrations" / "112_operational_json_canonical_store_tables.sql",
    REPO_ROOT / "supabase" / "migrations" / "113_space_operational_store_tables.sql",
    REPO_ROOT / "supabase" / "migrations" / "114_capex_analyses.sql",
    REPO_ROOT / "supabase" / "migrations" / "115_space_registry_and_settings.sql",
]


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with open(path) as handle:
        return json.load(handle)


def apply_migrations(cur):
    for path in SQL_MIGRATIONS:
        sql = path.read_text()
        try:
            cur.execute(sql)
        except errors.DuplicateObject:
            cur.connection.rollback()
            cur = cur.connection.cursor()
            continue
    return cur


def normalize_site_code(value: str | None) -> str | None:
    if not value:
        return value
    if re.fullmatch(r"S\d{3}", value):
        return f"site-{value[1:]}"
    return value.lower() if value.startswith("SITE-") else value


def migrate_agent_memory(cur) -> int:
    rows = load_json(AGENT_MEMORY_FILE, [])
    inserted = 0
    for row in rows:
        cur.execute(
            """
            INSERT INTO public.agent_memory (
                id, site_id, equipment_code, context_type, key, value, source,
                confidence, expires_at, created_at, updated_at
            ) VALUES (
                %(id)s, %(site_id)s, %(equipment_code)s, %(context_type)s, %(key)s, %(value)s, %(source)s,
                %(confidence)s, %(expires_at)s, %(created_at)s, %(updated_at)s
            )
            ON CONFLICT (id) DO UPDATE SET
                site_id = EXCLUDED.site_id,
                equipment_code = EXCLUDED.equipment_code,
                context_type = EXCLUDED.context_type,
                key = EXCLUDED.key,
                value = EXCLUDED.value,
                source = EXCLUDED.source,
                confidence = EXCLUDED.confidence,
                expires_at = EXCLUDED.expires_at,
                updated_at = EXCLUDED.updated_at
            """,
            row,
        )
        inserted += 1
    return inserted


def migrate_user_entitlements(cur) -> int:
    rows = load_json(USER_ENTITLEMENTS_FILE, {})
    inserted = 0
    for email, modules in rows.items():
        payload = {"user_id": email, "user_email": email, "modules": Json(modules)}
        cur.execute(
            """
            INSERT INTO public.user_entitlements (user_id, user_email, modules)
            VALUES (%(user_id)s, %(user_email)s, %(modules)s)
            ON CONFLICT (user_id) DO UPDATE SET
                user_email = EXCLUDED.user_email,
                modules = EXCLUDED.modules,
                updated_at = now()
            """,
            payload,
        )
        inserted += 1
    return inserted


def migrate_decision_memory(cur) -> tuple[int, int]:
    records = load_json(DECISION_RECORDS_FILE, [])
    patterns = load_json(DECISION_PATTERNS_FILE, [])

    for row in records:
        row = dict(row)
        row["action_details"] = Json(row.get("action_details", {}))
        row["signals_snapshot"] = Json(row.get("signals_snapshot", []))
        cur.execute(
            """
            INSERT INTO public.decision_records (
                record_id, event_type, event_description, equipment_id, equipment_type, site_id,
                diagnosis, diagnosis_confidence, diagnosis_source, action_type, action_details,
                action_executed_at, action_executed_by, outcome, outcome_details, outcome_evaluated_at,
                resolution_time_minutes, signals_snapshot, season, time_of_day, created_at, updated_at,
                correlation_id, recommendation_id, work_order_id, event_id
            ) VALUES (
                %(record_id)s, %(event_type)s, %(event_description)s, %(equipment_id)s, %(equipment_type)s, %(site_id)s,
                %(diagnosis)s, %(diagnosis_confidence)s, %(diagnosis_source)s, %(action_type)s, %(action_details)s,
                %(action_executed_at)s, %(action_executed_by)s, %(outcome)s, %(outcome_details)s, %(outcome_evaluated_at)s,
                %(resolution_time_minutes)s, %(signals_snapshot)s, %(season)s, %(time_of_day)s, %(created_at)s, %(updated_at)s,
                %(correlation_id)s, %(recommendation_id)s, %(work_order_id)s, %(event_id)s
            )
            ON CONFLICT (record_id) DO UPDATE SET
                updated_at = EXCLUDED.updated_at,
                outcome = EXCLUDED.outcome,
                outcome_details = EXCLUDED.outcome_details,
                outcome_evaluated_at = EXCLUDED.outcome_evaluated_at,
                resolution_time_minutes = EXCLUDED.resolution_time_minutes,
                action_details = EXCLUDED.action_details,
                signals_snapshot = EXCLUDED.signals_snapshot
            """,
            row,
        )

    for row in patterns:
        row = dict(row)
        row["action_details"] = Json(row.get("action_details", {}))
        row["applicable_sites"] = Json(row.get("applicable_sites", []))
        cur.execute(
            """
            INSERT INTO public.decision_patterns (
                pattern_id, event_type, equipment_type, likely_diagnosis, diagnosis_confidence,
                recommended_action, action_details, total_occurrences, resolved_count, success_rate,
                avg_resolution_time_minutes, applicable_sites, seasonal_pattern, created_at, updated_at, last_matched_at
            ) VALUES (
                %(pattern_id)s, %(event_type)s, %(equipment_type)s, %(likely_diagnosis)s, %(diagnosis_confidence)s,
                %(recommended_action)s, %(action_details)s, %(total_occurrences)s, %(resolved_count)s, %(success_rate)s,
                %(avg_resolution_time_minutes)s, %(applicable_sites)s, %(seasonal_pattern)s, %(created_at)s, %(updated_at)s, %(last_matched_at)s
            )
            ON CONFLICT (pattern_id) DO UPDATE SET
                updated_at = EXCLUDED.updated_at,
                diagnosis_confidence = EXCLUDED.diagnosis_confidence,
                recommended_action = EXCLUDED.recommended_action,
                action_details = EXCLUDED.action_details,
                total_occurrences = EXCLUDED.total_occurrences,
                resolved_count = EXCLUDED.resolved_count,
                success_rate = EXCLUDED.success_rate,
                avg_resolution_time_minutes = EXCLUDED.avg_resolution_time_minutes,
                applicable_sites = EXCLUDED.applicable_sites,
                last_matched_at = EXCLUDED.last_matched_at
            """,
            row,
        )

    return len(records), len(patterns)


def migrate_recommendations(cur) -> int:
    payload = load_json(RECOMMENDATIONS_FILE, {})
    rows = list(payload.get("recommendations", {}).values())
    inserted = 0
    for row in rows:
        row = dict(row)
        row["site_id"] = normalize_site_code(row.get("site_id"))
        row["action"] = Json(row.get("action", {}))
        row["expected_impact"] = Json(row.get("expected_impact", {}))
        row["execution_result"] = Json(row.get("execution_result")) if row.get("execution_result") is not None else None
        cur.execute(
            """
            INSERT INTO public.recommendations (
                id, site_id, timestamp, action_type, risk_level, target_equipment, action, reason,
                expected_impact, confidence, confidence_score, profile, multi_objective_score,
                status, requires_approval, approved_by, approval_reason, executed_at,
                execution_result, rejection_reason, outcome_validated, outcome_notes, outcome_validated_at
            ) VALUES (
                %(id)s::uuid, %(site_id)s, %(timestamp)s, %(action_type)s, %(risk_level)s, %(target_equipment)s, %(action)s, %(reason)s,
                %(expected_impact)s, %(confidence)s, %(confidence_score)s, %(profile)s, %(multi_objective_score)s,
                %(status)s, %(requires_approval)s, %(approved_by)s, %(approval_reason)s, %(executed_at)s,
                %(execution_result)s, %(rejection_reason)s, %(outcome_validated)s, %(outcome_notes)s, %(outcome_validated_at)s
            )
            ON CONFLICT (id) DO NOTHING
            """,
            row,
        )
        inserted += 1
    return inserted


def migrate_capex_analyses(cur) -> int:
    rows = load_json(CAPEX_ANALYSES_FILE, [])
    inserted = 0
    for row in rows:
        cur.execute(
            """
            INSERT INTO public.capex_analyses (
                id, equipment_code, equipment_type, recommendation, confidence_pct,
                npv_replace_zar, npv_repair_zar, npv_advantage_zar, replacement_cost_zar,
                repair_cost_zar, failure_probability, payback_months, risk_reduction_pct,
                discount_rate, horizon_years, analysis_date, created_at
            ) VALUES (
                %(id)s::uuid, %(equipment_code)s, %(equipment_type)s, %(recommendation)s, %(confidence_pct)s,
                %(npv_replace_zar)s, %(npv_repair_zar)s, %(npv_advantage_zar)s, %(replacement_cost_zar)s,
                %(repair_cost_zar)s, %(failure_probability)s, %(payback_months)s, %(risk_reduction_pct)s,
                %(discount_rate)s, %(horizon_years)s, %(analysis_date)s, %(created_at)s
            )
            ON CONFLICT (id) DO UPDATE SET
                equipment_code = EXCLUDED.equipment_code,
                equipment_type = EXCLUDED.equipment_type,
                recommendation = EXCLUDED.recommendation,
                confidence_pct = EXCLUDED.confidence_pct,
                npv_replace_zar = EXCLUDED.npv_replace_zar,
                npv_repair_zar = EXCLUDED.npv_repair_zar,
                npv_advantage_zar = EXCLUDED.npv_advantage_zar,
                replacement_cost_zar = EXCLUDED.replacement_cost_zar,
                repair_cost_zar = EXCLUDED.repair_cost_zar,
                failure_probability = EXCLUDED.failure_probability,
                payback_months = EXCLUDED.payback_months,
                risk_reduction_pct = EXCLUDED.risk_reduction_pct,
                discount_rate = EXCLUDED.discount_rate,
                horizon_years = EXCLUDED.horizon_years,
                analysis_date = EXCLUDED.analysis_date,
                created_at = EXCLUDED.created_at
            """,
            row,
        )
        inserted += 1
    return inserted


def migrate_sentinel_users(cur) -> int:
    payload = load_json(USERS_FILE, {})
    rows = payload.get("users", [])
    inserted = 0
    for row in rows:
        record = {
            "email": row["email"].strip().lower(),
            "full_name": row.get("full_name") or row["email"].split("@")[0].title(),
            "role": row.get("role", "auditor"),
            "is_active": row.get("is_active", True),
        }
        cur.execute(
            """
            INSERT INTO public.sentinel_users (email, full_name, role, is_active)
            VALUES (%(email)s, %(full_name)s, %(role)s, %(is_active)s)
            ON CONFLICT (email) DO UPDATE SET
                full_name = EXCLUDED.full_name,
                role = EXCLUDED.role,
                is_active = EXCLUDED.is_active,
                updated_at = now()
            """,
            record,
        )
        inserted += 1
    return inserted


def ensure_technician_exists(cur, technician_id: str) -> None:
    cur.execute("SELECT 1 FROM public.technicians WHERE id = %s::uuid", (technician_id,))
    if cur.fetchone():
        return

    suffix = technician_id.split("-")[0].upper()
    payload = {
        "id": technician_id,
        "code": f"TECH-LEGACY-{suffix}",
        "name": f"Legacy Technician {suffix}",
        "email": f"legacy-{suffix.lower()}@sentinel.local",
    }
    cur.execute(
        """
        INSERT INTO public.technicians (id, code, name, email, active)
        VALUES (%(id)s::uuid, %(code)s, %(name)s, %(email)s, true)
        ON CONFLICT (id) DO NOTHING
        """,
        payload,
    )


def migrate_notification_preferences(cur) -> int:
    payload = load_json(NOTIFICATION_PREFS_FILE, {})
    inserted = 0
    for record in payload.values():
        ensure_technician_exists(cur, record["technician_id"])
        record = dict(record)
        record["id"] = record["technician_id"]
        cur.execute(
            """
            INSERT INTO public.technician_notification_preferences (
                id, technician_id, preferred_channel, enabled_channels, alert_level_min,
                quiet_hours_enabled, quiet_hours_start, quiet_hours_end,
                emergency_override_enabled, batch_low_priority, batch_interval_minutes,
                created_at, updated_at
            ) VALUES (
                %(id)s::uuid, %(technician_id)s::uuid, %(preferred_channel)s, %(enabled_channels)s, %(alert_level_min)s,
                %(quiet_hours_enabled)s, %(quiet_hours_start)s, %(quiet_hours_end)s,
                %(emergency_override_enabled)s, %(batch_low_priority)s, %(batch_interval_minutes)s,
                %(created_at)s, %(updated_at)s
            )
            ON CONFLICT (technician_id) DO UPDATE SET
                preferred_channel = EXCLUDED.preferred_channel,
                enabled_channels = EXCLUDED.enabled_channels,
                alert_level_min = EXCLUDED.alert_level_min,
                quiet_hours_enabled = EXCLUDED.quiet_hours_enabled,
                quiet_hours_start = EXCLUDED.quiet_hours_start,
                quiet_hours_end = EXCLUDED.quiet_hours_end,
                emergency_override_enabled = EXCLUDED.emergency_override_enabled,
                batch_low_priority = EXCLUDED.batch_low_priority,
                batch_interval_minutes = EXCLUDED.batch_interval_minutes,
                updated_at = EXCLUDED.updated_at
            """,
            record,
        )
        inserted += 1
    return inserted


def migrate_notification_delivery_log(cur) -> int:
    payload = load_json(NOTIFICATION_DELIVERY_FILE, {})
    inserted = 0
    for records in payload.values():
        for record in records:
            row = dict(record)
            ensure_technician_exists(cur, row["technician_id"])
            row["provider_response"] = Json(row.get("provider_response", {}))
            cur.execute(
                """
                INSERT INTO public.notification_delivery_log (
                    id, work_order_id, technician_id, notification_type, title, body, channel_type,
                    recipient_identifier, status, error_message, error_code, external_message_id,
                    sent_at, delivered_at, provider, provider_response, retry_count, last_retry_at,
                    max_retries, created_at, updated_at
                ) VALUES (
                    %(id)s::uuid, NULLIF(%(work_order_id)s, '')::uuid, %(technician_id)s::uuid, %(notification_type)s, %(title)s, %(body)s, %(channel_type)s,
                    %(recipient_identifier)s, %(status)s, %(error_message)s, %(error_code)s, %(external_message_id)s,
                    %(sent_at)s, %(delivered_at)s, %(provider)s, %(provider_response)s, %(retry_count)s, %(last_retry_at)s,
                    %(max_retries)s, %(created_at)s, %(updated_at)s
                )
                ON CONFLICT (id) DO UPDATE SET
                    status = EXCLUDED.status,
                    error_message = EXCLUDED.error_message,
                    error_code = EXCLUDED.error_code,
                    external_message_id = EXCLUDED.external_message_id,
                    sent_at = EXCLUDED.sent_at,
                    delivered_at = EXCLUDED.delivered_at,
                    provider = EXCLUDED.provider,
                    provider_response = EXCLUDED.provider_response,
                    retry_count = EXCLUDED.retry_count,
                    last_retry_at = EXCLUDED.last_retry_at,
                    max_retries = EXCLUDED.max_retries,
                    updated_at = EXCLUDED.updated_at
                """,
                row,
            )
            inserted += 1
    return inserted


def migrate_space_occupancy(cur) -> int:
    rows = load_json(SPACE_OCCUPANCY_FILE, [])
    for row in rows:
        row = dict(row)
        row.setdefault("moving", None)
        row.setdefault("stationary", None)
        row.setdefault("distance_m", None)
        row.setdefault("moving_gate", None)
        row.setdefault("static_gate", None)
        cur.execute(
            """
            INSERT INTO public.space_occupancy_events (
                id, site_id, room_code, sensor_id, occupied, timestamp, source, received_at,
                moving, stationary, distance_m, moving_gate, static_gate
            ) VALUES (
                %(id)s, %(site_id)s, %(room_code)s, %(sensor_id)s, %(occupied)s, %(timestamp)s, %(source)s, %(received_at)s,
                %(moving)s, %(stationary)s, %(distance_m)s, %(moving_gate)s, %(static_gate)s
            )
            ON CONFLICT (id) DO NOTHING
            """,
            row,
        )
    return len(rows)


def migrate_space_ghost_findings(cur) -> int:
    rows = load_json(SPACE_GHOST_FILE, [])
    for row in rows:
        row = dict(row)
        row.setdefault("source_booking_flagged", False)
        row.setdefault("notification_sent_at", None)
        row.setdefault("resolved_at", None)
        row.setdefault("inspected_by", None)
        row.setdefault("inspected_at", None)
        row.setdefault("concierge_email", None)
        row.setdefault("concierge_whatsapp", None)
        row.setdefault("email_notified_at", None)
        row.setdefault("whatsapp_notified_at", None)
        row.setdefault("whatsapp_message_id", None)
        row.setdefault("response_message_id", None)
        row.setdefault("response_text", None)
        row.setdefault("reminder_sent", False)
        row.setdefault("reminder_sent_at", None)
        row.setdefault("cost_centre", None)
        row.setdefault("charge_amount", None)
        row.setdefault("charge_reason", None)
        cur.execute(
            """
            INSERT INTO public.ghost_findings (
                id, site_id, room_code, room_name, booking_id, organiser_email, organiser_name,
                source_booking_flagged, booking_start, booking_end, grace_period_minutes, detected_at,
                notification_sent, notification_sent_at, status, resolved_at, inspected_by, inspected_at,
                concierge_email, concierge_whatsapp, email_notified_at, whatsapp_notified_at,
                whatsapp_message_id, response_message_id, response_text, reminder_sent, reminder_sent_at,
                cost_centre, charge_amount, charge_reason
            ) VALUES (
                %(id)s, %(site_id)s, %(room_code)s, %(room_name)s, %(booking_id)s, %(organiser_email)s, %(organiser_name)s,
                %(source_booking_flagged)s, %(booking_start)s, %(booking_end)s, %(grace_period_minutes)s, %(detected_at)s,
                %(notification_sent)s, %(notification_sent_at)s, %(status)s, %(resolved_at)s, %(inspected_by)s, %(inspected_at)s,
                %(concierge_email)s, %(concierge_whatsapp)s, %(email_notified_at)s, %(whatsapp_notified_at)s,
                %(whatsapp_message_id)s, %(response_message_id)s, %(response_text)s, %(reminder_sent)s, %(reminder_sent_at)s,
                %(cost_centre)s, %(charge_amount)s, %(charge_reason)s
            )
            ON CONFLICT (id) DO UPDATE SET
                status = EXCLUDED.status,
                notification_sent = EXCLUDED.notification_sent,
                notification_sent_at = EXCLUDED.notification_sent_at,
                resolved_at = EXCLUDED.resolved_at,
                inspected_by = EXCLUDED.inspected_by,
                inspected_at = EXCLUDED.inspected_at,
                concierge_email = EXCLUDED.concierge_email,
                concierge_whatsapp = EXCLUDED.concierge_whatsapp,
                email_notified_at = EXCLUDED.email_notified_at,
                whatsapp_notified_at = EXCLUDED.whatsapp_notified_at,
                whatsapp_message_id = EXCLUDED.whatsapp_message_id,
                response_message_id = EXCLUDED.response_message_id,
                response_text = EXCLUDED.response_text,
                reminder_sent = EXCLUDED.reminder_sent,
                reminder_sent_at = EXCLUDED.reminder_sent_at,
                cost_centre = EXCLUDED.cost_centre,
                charge_amount = EXCLUDED.charge_amount,
                charge_reason = EXCLUDED.charge_reason
            """,
            row,
        )
    return len(rows)


def migrate_space_room_state(cur) -> tuple[int, int, int, int]:
    room_events = load_json(SPACE_ROOM_EVENTS_FILE, [])
    current_states = load_json(SPACE_CURRENT_STATE_FILE, [])
    rightsizing = load_json(SPACE_RIGHTSIZING_FILE, [])
    focus_sessions = load_json(SPACE_FOCUS_SESSIONS_FILE, [])

    for row in room_events:
        cur.execute(
            """
            INSERT INTO public.space_room_events (
                id, site_id, room_code, sensor_id, occupied, timestamp, source, received_at,
                moving, stationary, distance_m, moving_gate, static_gate
            ) VALUES (
                %(id)s, %(site_id)s, %(room_code)s, %(sensor_id)s, %(occupied)s, %(timestamp)s, %(source)s, %(received_at)s,
                %(moving)s, %(stationary)s, %(distance_m)s, %(moving_gate)s, %(static_gate)s
            )
            ON CONFLICT (id) DO NOTHING
            """,
            row,
        )

    for row in current_states:
        payload = {
            "room_code": row.get("room_code"),
            "site_id": row.get("site_id"),
            "sensor_id": row.get("sensor_id"),
            "occupied": row.get("occupied", False),
            "last_event_at": row.get("last_event_at") or row.get("updated_at"),
            "updated_at": row.get("updated_at"),
            "state": Json(row),
        }
        cur.execute(
            """
            INSERT INTO public.space_room_current_state (
                room_code, site_id, sensor_id, occupied, last_event_at, updated_at, state
            ) VALUES (
                %(room_code)s, %(site_id)s, %(sensor_id)s, %(occupied)s, %(last_event_at)s, %(updated_at)s, %(state)s
            )
            ON CONFLICT (room_code) DO UPDATE SET
                site_id = EXCLUDED.site_id,
                sensor_id = EXCLUDED.sensor_id,
                occupied = EXCLUDED.occupied,
                last_event_at = EXCLUDED.last_event_at,
                updated_at = EXCLUDED.updated_at,
                state = EXCLUDED.state
            """,
            payload,
        )

    for row in rightsizing:
        cur.execute(
            """
            INSERT INTO public.space_rightsizing_findings (
                id, site_id, room_code, room_name, room_capacity, booking_id, organiser_email, organiser_name,
                booking_start, booking_end, booking_duration_minutes, occupied_minutes, vacancy_started_at,
                consecutive_vacancy_minutes, pattern_type, detected_at, notification_sent, notification_sent_at, status
            ) VALUES (
                %(id)s, %(site_id)s, %(room_code)s, %(room_name)s, %(room_capacity)s, %(booking_id)s, %(organiser_email)s, %(organiser_name)s,
                %(booking_start)s, %(booking_end)s, %(booking_duration_minutes)s, %(occupied_minutes)s, %(vacancy_started_at)s,
                %(consecutive_vacancy_minutes)s, %(pattern_type)s, %(detected_at)s, %(notification_sent)s, %(notification_sent_at)s, %(status)s
            )
            ON CONFLICT (id) DO UPDATE SET
                status = EXCLUDED.status,
                notification_sent = EXCLUDED.notification_sent,
                notification_sent_at = EXCLUDED.notification_sent_at
            """,
            row,
        )

    for row in focus_sessions:
        cur.execute(
            """
            INSERT INTO public.space_focus_room_sessions (
                session_id, site_id, room_code, room_type, sensor_id, source, start_time,
                end_time, duration_seconds, extended_use, created_at
            ) VALUES (
                %(session_id)s, %(site_id)s, %(room_code)s, %(room_type)s, %(sensor_id)s, %(source)s, %(start_time)s,
                %(end_time)s, %(duration_seconds)s, %(extended_use)s, %(created_at)s
            )
            ON CONFLICT (session_id) DO UPDATE SET
                end_time = EXCLUDED.end_time,
                duration_seconds = EXCLUDED.duration_seconds,
                extended_use = EXCLUDED.extended_use
            """,
            row,
        )

    return len(room_events), len(current_states), len(rightsizing), len(focus_sessions)


def upsert_system_setting(cur, key: str, value: Any, *, category: str, description: str, is_public: bool = False) -> None:
    cur.execute(
        """
        INSERT INTO public.system_settings (
            key, value, category, description, data_type, is_public, is_editable
        ) VALUES (
            %s, %s, %s, %s, 'object', %s, true
        )
        ON CONFLICT (key) DO UPDATE SET
            value = EXCLUDED.value,
            category = EXCLUDED.category,
            description = EXCLUDED.description,
            is_public = EXCLUDED.is_public,
            updated_at = now()
        """,
        (key, Json(value), category, description, is_public),
    )


def migrate_space_registry(cur) -> tuple[int, int, int, int]:
    concierges = load_json(SPACE_CONCIERGES_FILE, [])
    room_registry = load_json(SPACE_ROOM_REGISTRY_FILE, [])
    sensor_devices = load_json(SPACE_SENSOR_DEVICES_FILE, [])
    site_structure = load_json(SPACE_SITE_STRUCTURE_FILE, [])
    space_settings = load_json(SPACE_SETTINGS_FILE, None)

    for row in concierges:
        payload = dict(row)
        payload.setdefault("id", str(uuid.uuid4()))
        payload["building_codes"] = Json(payload.get("building_codes", []))
        payload["floor_assignments"] = Json(payload.get("floor_assignments", {}))
        cur.execute(
            """
            INSERT INTO public.space_concierges (
                id, name, mobile, email, site_id, building_codes,
                floor_assignments, active, created_at, updated_at
            ) VALUES (
                %(id)s::uuid, %(name)s, %(mobile)s, %(email)s, %(site_id)s, %(building_codes)s,
                %(floor_assignments)s, %(active)s, %(created_at)s, %(updated_at)s
            )
            ON CONFLICT (id) DO UPDATE SET
                name = EXCLUDED.name,
                mobile = EXCLUDED.mobile,
                email = EXCLUDED.email,
                site_id = EXCLUDED.site_id,
                building_codes = EXCLUDED.building_codes,
                floor_assignments = EXCLUDED.floor_assignments,
                active = EXCLUDED.active,
                updated_at = EXCLUDED.updated_at
            """,
            payload,
        )

    for row in room_registry:
        payload = dict(row)
        cur.execute(
            """
            INSERT INTO public.room_registry (
                site_id, room_id, building, quadrant, room_type, room_number,
                capacity, floor, friendly_name, active
            ) VALUES (
                %(site_id)s, %(room_id)s, %(building)s, %(quadrant)s, %(room_type)s, %(room_number)s,
                %(capacity)s, %(floor)s, %(friendly_name)s, %(active)s
            )
            ON CONFLICT (room_id) DO UPDATE SET
                site_id = EXCLUDED.site_id,
                building = EXCLUDED.building,
                quadrant = EXCLUDED.quadrant,
                room_type = EXCLUDED.room_type,
                room_number = EXCLUDED.room_number,
                capacity = EXCLUDED.capacity,
                floor = EXCLUDED.floor,
                friendly_name = EXCLUDED.friendly_name,
                active = EXCLUDED.active
            """,
            payload,
        )

    for row in sensor_devices:
        payload = dict(row)
        payload.setdefault("enabled", True)
        payload.setdefault("sensor_online", False)
        payload.setdefault("firmware_version", None)
        payload.setdefault("last_seen_at", None)
        payload.setdefault("last_rssi", None)
        payload.setdefault("uptime_seconds", None)
        cur.execute(
            """
            INSERT INTO public.space_sensor_devices (
                sensor_id, device_token, room_code, site_id, enabled, firmware_version,
                last_seen_at, last_rssi, uptime_seconds, sensor_online
            ) VALUES (
                %(sensor_id)s, %(device_token)s, %(room_code)s, %(site_id)s, %(enabled)s, %(firmware_version)s,
                %(last_seen_at)s, %(last_rssi)s, %(uptime_seconds)s, %(sensor_online)s
            )
            ON CONFLICT (sensor_id) DO UPDATE SET
                device_token = EXCLUDED.device_token,
                room_code = EXCLUDED.room_code,
                site_id = EXCLUDED.site_id,
                enabled = EXCLUDED.enabled,
                firmware_version = EXCLUDED.firmware_version,
                last_seen_at = EXCLUDED.last_seen_at,
                last_rssi = EXCLUDED.last_rssi,
                uptime_seconds = EXCLUDED.uptime_seconds,
                sensor_online = EXCLUDED.sensor_online,
                updated_at = now()
            """,
            payload,
        )

    if site_structure:
        upsert_system_setting(
            cur,
            "space_site_structure",
            site_structure,
            category="space",
            description="Site/building/floor structure for space concierge assignment and UI dropdowns",
            is_public=False,
        )

    upsert_system_setting(
        cur,
        "space_settings",
        space_settings or DEFAULT_SPACE_SETTINGS,
        category="space",
        description="Space optimization operational settings",
        is_public=False,
    )

    return len(concierges), len(room_registry), len(sensor_devices), len(site_structure)


def main() -> int:
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False
    cur = conn.cursor()

    try:
        cur = apply_migrations(cur)

        summary = {
            "agent_memory": migrate_agent_memory(cur),
            "user_entitlements": migrate_user_entitlements(cur),
            "recommendations": migrate_recommendations(cur),
            "capex_analyses": migrate_capex_analyses(cur),
            "sentinel_users": migrate_sentinel_users(cur),
            "notification_preferences": migrate_notification_preferences(cur),
            "notification_delivery_log": migrate_notification_delivery_log(cur),
            "space_occupancy_events": migrate_space_occupancy(cur),
            "ghost_findings": migrate_space_ghost_findings(cur),
        }
        decision_records, decision_patterns = migrate_decision_memory(cur)
        summary["decision_records"] = decision_records
        summary["decision_patterns"] = decision_patterns
        room_events, room_current_state, rightsizing_findings, focus_room_sessions = migrate_space_room_state(cur)
        summary["space_room_events"] = room_events
        summary["space_room_current_state"] = room_current_state
        summary["space_rightsizing_findings"] = rightsizing_findings
        summary["space_focus_room_sessions"] = focus_room_sessions
        space_concierges, room_registry, sensor_devices, site_structure = migrate_space_registry(cur)
        summary["space_concierges"] = space_concierges
        summary["room_registry"] = room_registry
        summary["space_sensor_devices"] = sensor_devices
        summary["space_site_structure"] = site_structure

        conn.commit()

        print("Operational JSON migration complete")
        for key, value in summary.items():
            print(f"- {key}: {value}")
        return 0
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
