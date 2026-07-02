#!/usr/bin/env python3
"""Batch-onboard pending bridge discoveries for the fake S005 reset drill.

This script uses the existing system health onboarding endpoint contract for
each discovery. It is fake-site-only and defaults to dry-run.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

SITE_CODE = "site-005"


TYPE_MAP = {
    "AHU": "ahu",
    "BESS": "bess",
    "BOILER": "boiler",
    "CCURE": "access_control_server",
    "CHILLER": "chiller",
    "COLD": "cold_room",
    "CT": "cooling_tower",
    "DB": "distribution_board",
    "DOOR": "access_control_point",
    "FCU": "fcu",
    "FIRE": "fire_panel",
    "GATE": "access_control_point",
    "GEN": "generator",
    "JACE": "bms_controller",
    "KEF": "exhaust_fan",
    "LIFT": "lift",
    "MEDGAS": "medical_gas",
    "MSB": "switchboard",
    "PUMP": "pump",
    "PV": "pv",
    "SPLIT": "split",
    "UPS": "ups",
    "WATER": "water_meter",
    "ZONE": "zone_controller",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Dry-run or onboard pending S005 bridge discoveries.")
    parser.add_argument("--execute", action="store_true", help="Actually onboard pending discoveries.")
    parser.add_argument(
        "--confirm-fake-site-onboard",
        default="",
        help="Must be exactly site-005 when --execute is used.",
    )
    parser.add_argument("--limit", type=int, default=500, help="Maximum pending discoveries to process.")
    return parser.parse_args()


def _supabase():
    from app.database.supabase_client import get_supabase_client

    return get_supabase_client()


def _infer_type(code: str) -> str:
    value = str(code or "").strip()
    upper = value.upper()
    raw = re.search(r"(?:S\d{3}-)?SITE-\d{3}-[^-]+-([A-Z]+)-", upper)
    if raw:
        token = raw.group(1)
    else:
        parts = upper.split("-")
        token = parts[1] if len(parts) > 2 and parts[0].startswith("S") else ""
    if token == "PV" and "INV" in upper:
        return "pv_inverter"
    if token == "PV" and "ARRAY" in upper:
        return "pv_array"
    return TYPE_MAP.get(token, token.lower() if token else "unknown")


def _pending(limit: int) -> list[dict[str, Any]]:
    sb = _supabase()
    result = (
        sb.table("bridge_discovered_equipment")
        .select("id, bridge_code, canonical_code, equipment_type, status")
        .eq("site_id", SITE_CODE)
        .eq("status", "pending")
        .order("canonical_code")
        .limit(limit)
        .execute()
    )
    return result.data or []


def _dry_run(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_type: dict[str, int] = {}
    samples: list[dict[str, Any]] = []
    for row in rows:
        inferred = _infer_type(row.get("canonical_code") or row.get("bridge_code") or "")
        by_type[inferred] = by_type.get(inferred, 0) + 1
        if len(samples) < 25:
            samples.append(
                {
                    "id": row.get("id"),
                    "canonical_code": row.get("canonical_code"),
                    "bridge_code": row.get("bridge_code"),
                    "inferred_type": inferred,
                }
            )
    return {
        "site_id": SITE_CODE,
        "mode": "dry_run",
        "pending": len(rows),
        "inferred_type_counts": dict(sorted(by_type.items())),
        "sample": samples,
    }


async def _execute(rows: list[dict[str, Any]]) -> dict[str, Any]:
    from app.api.system_health import OnboardDiscoveredEquipmentRequest, onboard_discovered_equipment

    results = []
    for row in rows:
        inferred = _infer_type(row.get("canonical_code") or row.get("bridge_code") or "")
        response = await onboard_discovered_equipment(
            SITE_CODE,
            row["id"],
            OnboardDiscoveredEquipmentRequest(equipment_type=inferred),
        )
        results.append(
            {
                "id": row["id"],
                "canonical_code": row.get("canonical_code"),
                "inferred_type": inferred,
                "success": response.success,
                "message": response.message,
            }
        )
    return {
        "site_id": SITE_CODE,
        "mode": "execute",
        "processed": len(results),
        "results": results[:25],
        "result_sample_truncated": len(results) > 25,
    }


async def amain() -> int:
    args = parse_args()
    if args.execute and args.confirm_fake_site_onboard != SITE_CODE:
        print("ERROR: --execute requires --confirm-fake-site-onboard site-005", file=sys.stderr)
        return 2

    rows = _pending(args.limit)
    if not args.execute:
        print(json.dumps(_dry_run(rows), indent=2, sort_keys=True))
        return 0

    print(json.dumps(await _execute(rows), indent=2, sort_keys=True))
    return 0


def main() -> int:
    return asyncio.run(amain())


if __name__ == "__main__":
    raise SystemExit(main())
