#!/usr/bin/env python3
"""Re-onboard fake site-005 after the reset drill.

This recreates only the starting control-plane scaffolding:
- sites row via SiteCreationService with manual site_code=site-005
- phase promotion gates
- base mandatory modules
- bridge adapter config
- local building skeleton + active-site registry entry
- mode policy files

It intentionally does not restore old equipment, telemetry, zones, model
registry entries, or learned patterns.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

SITE_CODE = "site-005"
SITE_NAME = "Busamed Gateway Private Hospital"
SITE_ADDRESS = "36-38 Aurora Dr, Umhlanga Rocks, uMhlanga, 4319"
SITE_REGION = "KwaZulu-Natal"
SITE_TYPE = "hospital"
SITE_FLOORS = ["B1", "G", "L1", "L2", "L3", "L4", "L5", "L6", "L7", "L8", "L9"]
SITE_SQM = 15000
SITE_YEAR_BUILT = 2010
SITE_LATITUDE = -29.7286
SITE_LONGITUDE = 31.0689
SITE_NMD_KVA = 8000.0
BASE_MODULES = (
    "kpi",
    "ml",
    "notifications",
    "integrations",
    "simbiot",
    "logging",
    "assets",
    "hvac",
    "energy",
    "lighting",
    "solar",
    "water",
    "fire",
    "security",
    "digital_twin",
)

SITES_DIR = BACKEND_ROOT / "app" / "data" / "sites"
SITE_DIR = SITES_DIR / SITE_CODE
SITE_REGISTRY_PATH = SITES_DIR / "_registry.json"
POLICY_DIR = BACKEND_ROOT / "app" / "data" / "policies"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Dry-run or execute fake S005 re-onboarding.")
    parser.add_argument("--execute", action="store_true", help="Actually recreate site-005 scaffolding.")
    parser.add_argument(
        "--confirm-fake-site-reonboard",
        default="",
        help="Must be exactly site-005 when --execute is used.",
    )
    return parser.parse_args()


def _supabase():
    from app.database.supabase_client import get_supabase_client

    return get_supabase_client()


def _site_exists() -> bool:
    sb = _supabase()
    result = sb.table("sites").select("id, code").eq("code", SITE_CODE).limit(1).execute()
    return bool(result.data)


def _local_state() -> dict[str, Any]:
    registry: dict[str, Any] = {}
    if SITE_REGISTRY_PATH.exists():
        registry = json.loads(SITE_REGISTRY_PATH.read_text())
    return {
        "site_row_exists": _site_exists(),
        "site_dir_exists": SITE_DIR.exists(),
        "registry_active_contains_site": SITE_CODE in registry.get("active_sites", []),
        "mode_policy_exists": (POLICY_DIR / f"{SITE_CODE}-mode-policy.json").exists(),
        "mode_policy_state_exists": (POLICY_DIR / f"{SITE_CODE}-mode-policy-state.json").exists(),
    }


def _create_site_row() -> dict[str, Any]:
    from app.services.site_creation_service import SiteCreationService

    service = SiteCreationService()
    site = service.create_site(
        site_name=SITE_NAME,
        building_type=SITE_TYPE,
        location=SITE_ADDRESS,
        gross_floor_area=SITE_SQM,
        year_built=SITE_YEAR_BUILT,
        latitude=SITE_LATITUDE,
        longitude=SITE_LONGITUDE,
        nmd_limit_kva=SITE_NMD_KVA,
        operating_hours={"weekday": "00:00-23:59", "weekend": "00:00-23:59"},
        optimization_settings={
            "profile": "hospital_continuity_first",
            "comfort_priority": "clinical_safety",
            "savings_priority": "secondary",
        },
        site_code=SITE_CODE,
        enabled=True,
        onboarding_phase="shadow_live",
    )

    sb = _supabase()
    sb.table("sites").update(
        {
            "region": SITE_REGION,
            "floors": len(SITE_FLOORS),
            "floor_labels": SITE_FLOORS,
            "equipment_count": 0,
            "sentinel_processing_enabled": False,
        }
    ).eq("code", SITE_CODE).execute()
    return site


def _seed_modules() -> list[str]:
    from app.services.module_registry_service import module_registry

    seeded = list(module_registry.ensure_base_modules(SITE_CODE, SITE_NAME) or [])
    sb = _supabase()
    existing = sb.table("site_modules").select("module_type").eq("site_id", SITE_CODE).execute()
    existing_types = {row["module_type"] for row in existing.data or []}
    if existing_types:
        return seeded

    now = datetime.now(UTC).isoformat()
    sb.table("site_module_configs").upsert(
        {
            "site_id": SITE_CODE,
            "site_name": SITE_NAME,
            "ai_enabled": True,
            "auto_integration": True,
            "updated_at": now,
        },
        on_conflict="site_id",
    ).execute()

    rows: list[dict[str, Any]] = []
    for module_type in BASE_MODULES:
        config: dict[str, Any] = {}
        if module_type == "fire":
            config = {
                "auto_mode": False,
                "commissioned_cause_effect": False,
                "authority": "fire_panel_and_bms",
                "sentinel_role": "monitoring_only",
            }
        rows.append(
            {
                "instance_id": f"{SITE_CODE}-{module_type}-{uuid.uuid4().hex[:8]}",
                "site_id": SITE_CODE,
                "module_type": module_type,
                "status": "active",
                "activated_at": now,
                "config": config,
                "health_score": 100.0,
                "licensed": True,
                "connected": False,
                "updated_at": now,
            }
        )
    sb.table("site_modules").upsert(rows, on_conflict="instance_id").execute()
    return [str(row["module_type"]) for row in rows]


def _seed_adapter_config() -> dict[str, Any]:
    sb = _supabase()
    bridge_token = (
        os.environ.get("BRIDGE_API_TOKEN_SITE005")
        or os.environ.get("BRIDGE_API_TOKEN_SITE_005")
        or os.environ.get("BRIDGE_API_TOKEN")
        or os.environ.get("SIMBIOT_API_KEY", "")
    )
    payload = {
        "site_id": SITE_CODE,
        "protocol": "bridge",
        "enabled": True,
        "connection_config": {
            "base_url": "http://10.99.0.1:8080",
            "token": bridge_token,
            "supports_writes": False,
            "write_enabled": False,
            "timeout_seconds": 30.0,
        },
        "poll_interval_seconds": 300,
    }
    result = sb.table("site_adapter_config").upsert(payload, on_conflict="site_id,protocol").execute()
    return result.data[0] if result.data else payload


def _write_local_site_files() -> None:
    equipment_dir = SITE_DIR / "equipment"
    equipment_dir.mkdir(parents=True, exist_ok=True)
    building_json = {
        "id": SITE_CODE,
        "name": SITE_NAME,
        "display_name": SITE_NAME,
        "address": SITE_ADDRESS,
        "timezone": "Africa/Johannesburg",
        "floors": SITE_FLOORS,
        "features": {
            "hvac": True,
            "dali": True,
            "desk_diagnosis": False,
            "load_shedding_optimization": True,
            "clinical_continuity": True,
        },
        "bms": {
            "vendor": "Unknown",
            "system": "SIMBIOT bridge",
            "protocol": "Bridge",
        },
        "contacts": {
            "email": "",
            "emergency": "",
            "whatsapp": "",
        },
        "metadata": {
            "type": SITE_TYPE,
            "region": SITE_REGION,
            "total_floors": len(SITE_FLOORS),
            "sqm": SITE_SQM,
            "year_built": SITE_YEAR_BUILT,
            "equipment_count": 0,
            "total_devices": 0,
            "on_bms_count": 0,
            "bms_coverage_pct": 0,
            "onboarding_phase": "shadow_live",
            "reset_generation_started_at": datetime.now(UTC).isoformat(),
        },
        "year_built": SITE_YEAR_BUILT,
        "latitude": SITE_LATITUDE,
        "longitude": SITE_LONGITUDE,
        "operating_hours": {"weekday": "00:00-23:59", "weekend": "00:00-23:59"},
    }
    (SITE_DIR / "building.json").write_text(json.dumps(building_json, indent=2) + "\n")

    if SITE_REGISTRY_PATH.exists():
        registry = json.loads(SITE_REGISTRY_PATH.read_text())
    else:
        registry = {"active_sites": [], "inactive_sites": [], "default_building": "site-002"}
    registry.setdefault("active_sites", [])
    if SITE_CODE not in registry["active_sites"]:
        registry["active_sites"].append(SITE_CODE)
    registry["active_sites"] = sorted(registry["active_sites"])
    registry.setdefault("inactive_sites", [])
    registry["inactive_sites"] = [site for site in registry["inactive_sites"] if site != SITE_CODE]
    registry.setdefault("default_building", "site-002")
    SITE_REGISTRY_PATH.write_text(json.dumps(registry, indent=2) + "\n")


def _write_mode_policies() -> None:
    POLICY_DIR.mkdir(parents=True, exist_ok=True)
    policy_state = {
        "site_id": SITE_CODE,
        "current_stage": "shadow_live",
        "candidate_stage": None,
        "candidate_since": None,
        "violation_stage": None,
        "violation_since": None,
        "last_demoted_at": None,
        "last_evaluated_at": None,
    }
    (POLICY_DIR / f"{SITE_CODE}-mode-policy-state.json").write_text(json.dumps(policy_state, indent=2) + "\n")

    src = POLICY_DIR / "site-002-mode-policy.json"
    dst = POLICY_DIR / f"{SITE_CODE}-mode-policy.json"
    if src.exists():
        shutil.copy2(src, dst)
        policy = json.loads(dst.read_text())
        policy["site_id"] = SITE_CODE
        policy["default_stage"] = "shadow_live"
        dst.write_text(json.dumps(policy, indent=2) + "\n")


def execute_reonboard() -> dict[str, Any]:
    before = _local_state()
    if before["site_row_exists"]:
        raise RuntimeError(f"{SITE_CODE} already exists; run the reset verification before re-onboarding")

    site = _create_site_row()
    modules = _seed_modules()
    adapter = _seed_adapter_config()
    _write_local_site_files()
    _write_mode_policies()

    return {
        "mode": "execute",
        "before": before,
        "site": site,
        "seeded_modules": modules,
        "adapter_protocol": adapter.get("protocol"),
        "adapter_enabled": adapter.get("enabled"),
        "after": _local_state(),
    }


def main() -> int:
    args = parse_args()
    if args.execute and args.confirm_fake_site_reonboard != SITE_CODE:
        print("ERROR: --execute requires --confirm-fake-site-reonboard site-005", file=sys.stderr)
        return 2

    if not args.execute:
        print(
            json.dumps({"mode": "dry_run", "site_code": SITE_CODE, "state": _local_state()}, indent=2, sort_keys=True)
        )
        return 0

    print(json.dumps(execute_reonboard(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
