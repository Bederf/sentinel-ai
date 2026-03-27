#!/usr/bin/env python3
"""Seed Phase 174 P0 runtime-authority data into local Postgres.

Scope is intentionally narrow:
- system_settings values sourced from backend/app/data/settings.json
- equipment_health_configs sourced from backend/app/data/health_calculation_config.json
- alert_routing_rules sourced from backend/app/data/alert_routing_rules.json

This script does not seed alert mutes, simulation data, onboarding artifacts,
or site-processing sidecar state.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import psycopg2
from psycopg2.extras import Json


REPO_ROOT = Path(__file__).resolve().parents[1]
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:55322/postgres")

SETTINGS_FILE = REPO_ROOT / "backend" / "app" / "data" / "settings.json"
HEALTH_CONFIG_FILE = REPO_ROOT / "backend" / "app" / "data" / "health_calculation_config.json"
ALERT_ROUTING_FILE = REPO_ROOT / "backend" / "app" / "data" / "alert_routing_rules.json"
P0_MIGRATION_FILE = REPO_ROOT / "supabase" / "migrations" / "20260325_004_runtime_authority_p0.sql"

SETTINGS_SPECS = {
    "healthThresholds": {
        "db_key": "health_thresholds",
        "category": "health",
        "description": "Health score thresholds for equipment classification (0-100 scale)",
        "is_public": True,
    },
    "riskThresholds": {
        "db_key": "risk_thresholds",
        "category": "risk",
        "description": "Risk score thresholds for cockpit severity interpretation (0-100 scale)",
        "is_public": True,
    },
    "notifications": {
        "db_key": "notifications",
        "category": "notifications",
        "description": "Runtime notification settings and alert command configuration",
        "is_public": False,
    },
    "display": {
        "db_key": "display",
        "category": "display",
        "description": "Display configuration for runtime UI surfaces",
        "is_public": True,
    },
    "controlLimits": {
        "db_key": "control_limits",
        "category": "controls",
        "description": "Runtime control limits used by shipped HVAC and chat control surfaces",
        "is_public": False,
    },
}


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with open(path) as handle:
        return json.load(handle)


def apply_p0_migration(cur) -> None:
    sql = P0_MIGRATION_FILE.read_text()
    cur.execute(sql)


def seed_system_settings(cur) -> int:
    settings = load_json(SETTINGS_FILE, {})
    seeded = 0

    for json_key, spec in SETTINGS_SPECS.items():
        if json_key not in settings:
            continue
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
            (
                spec["db_key"],
                Json(settings[json_key]),
                spec["category"],
                spec["description"],
                spec["is_public"],
            ),
        )
        seeded += 1

    return seeded


def seed_equipment_health_configs(cur) -> int:
    configs = load_json(HEALTH_CONFIG_FILE, {})
    seeded = 0

    for equipment_type, config in configs.items():
        payload = dict(config)
        payload["equipment_type"] = payload.get("equipment_type", equipment_type).strip().lower()
        cur.execute(
            """
            INSERT INTO public.equipment_health_configs (
                equipment_type, expected_life_years, service_interval_days,
                weights, thresholds, fault_weights
            ) VALUES (
                %(equipment_type)s, %(expected_life_years)s, %(service_interval_days)s,
                %(weights)s, %(thresholds)s, %(fault_weights)s
            )
            ON CONFLICT (equipment_type) DO UPDATE SET
                expected_life_years = EXCLUDED.expected_life_years,
                service_interval_days = EXCLUDED.service_interval_days,
                weights = EXCLUDED.weights,
                thresholds = EXCLUDED.thresholds,
                fault_weights = EXCLUDED.fault_weights,
                updated_at = now()
            """,
            {
                "equipment_type": payload["equipment_type"],
                "expected_life_years": payload["expected_life_years"],
                "service_interval_days": payload["service_interval_days"],
                "weights": Json(payload["weights"]),
                "thresholds": Json(payload["thresholds"]),
                "fault_weights": Json(payload.get("fault_weights")) if payload.get("fault_weights") is not None else None,
            },
        )
        seeded += 1

    return seeded


def seed_alert_routing_rules(cur) -> int:
    rules = load_json(ALERT_ROUTING_FILE, [])
    seeded = 0

    for rule in rules:
        payload = dict(rule)
        cur.execute(
            """
            INSERT INTO public.alert_routing_rules (
                id, name, enabled, severity, equipment_types, site_ids, channels,
                recipient_roles, recipient_ids, escalation_minutes, escalation_to_roles,
                created_at, updated_at, created_by, updated_by
            ) VALUES (
                %(id)s::uuid, %(name)s, %(enabled)s, %(severity)s, %(equipment_types)s, %(site_ids)s, %(channels)s,
                %(recipient_roles)s, %(recipient_ids)s, %(escalation_minutes)s, %(escalation_to_roles)s,
                %(created_at)s, %(updated_at)s, %(created_by)s, %(updated_by)s
            )
            ON CONFLICT (id) DO UPDATE SET
                name = EXCLUDED.name,
                enabled = EXCLUDED.enabled,
                severity = EXCLUDED.severity,
                equipment_types = EXCLUDED.equipment_types,
                site_ids = EXCLUDED.site_ids,
                channels = EXCLUDED.channels,
                recipient_roles = EXCLUDED.recipient_roles,
                recipient_ids = EXCLUDED.recipient_ids,
                escalation_minutes = EXCLUDED.escalation_minutes,
                escalation_to_roles = EXCLUDED.escalation_to_roles,
                updated_at = COALESCE(EXCLUDED.updated_at, now()),
                updated_by = EXCLUDED.updated_by
            """,
            {
                "id": payload["id"],
                "name": payload["name"],
                "enabled": payload.get("enabled", True),
                "severity": Json(payload.get("severity", [])),
                "equipment_types": Json(payload.get("equipment_types", [])),
                "site_ids": Json(payload.get("site_ids", [])),
                "channels": Json(payload.get("channels", [])),
                "recipient_roles": Json(payload.get("recipient_roles", [])),
                "recipient_ids": Json(payload.get("recipient_ids", [])),
                "escalation_minutes": payload.get("escalation_minutes"),
                "escalation_to_roles": Json(payload.get("escalation_to_roles", [])),
                "created_at": payload.get("created_at"),
                "updated_at": payload.get("updated_at", payload.get("created_at")),
                "created_by": payload.get("created_by"),
                "updated_by": payload.get("updated_by"),
            },
        )
        seeded += 1

    return seeded


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed Phase 174 P0 runtime-authority values into Postgres")
    parser.add_argument("--database-url", default=DATABASE_URL, help="Postgres connection string")
    parser.add_argument(
        "--apply-migration",
        action="store_true",
        help="Apply supabase/migrations/20260325_004_runtime_authority_p0.sql before seeding",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run inserts/updates in a transaction and roll them back at the end",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    with psycopg2.connect(args.database_url) as conn:
        with conn.cursor() as cur:
            if args.apply_migration:
                apply_p0_migration(cur)

            seeded_settings = seed_system_settings(cur)
            seeded_health_configs = seed_equipment_health_configs(cur)
            seeded_routing_rules = seed_alert_routing_rules(cur)

            if args.dry_run:
                conn.rollback()
                mode = "DRY RUN"
            else:
                conn.commit()
                mode = "COMMITTED"

    print(f"{mode}: system_settings={seeded_settings}, equipment_health_configs={seeded_health_configs}, alert_routing_rules={seeded_routing_rules}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
