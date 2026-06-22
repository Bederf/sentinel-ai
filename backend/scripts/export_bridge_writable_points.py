#!/usr/bin/env python3
"""Export verified writable SIMBIOT mappings for a bridge whitelist file.

The bridge is the final physical-write boundary. SENTINEL can mark a mapping
as verified in Supabase, but the bridge must still allow the exact object_id in
/opt/sites/{site_id}/config/bridge_writable_points.json.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("SITE_ID", "site-002")
os.environ.setdefault("PLANT_SITE_ID", "site-002")
os.environ.setdefault("BUILDING_NAME", "Sentinel Site")


def _load_backend_env() -> None:
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_backend_env()

WRITABLE_TYPE_TOKENS = ("analogoutput", "binaryoutput", "multistateoutput")
WRITABLE_TYPE_PREFIXES = ("command:", "setpoint:", "writable:")


def _site_code(raw: str) -> str:
    value = raw.strip()
    if value.startswith("site-"):
        return value
    if value.upper().startswith("S"):
        return f"site-{value[1:]}"
    return f"site-{value}"


def _is_writable(parameter_type: str | None) -> bool:
    text = (parameter_type or "").lower()
    return (
        text in {"command", "setpoint", "writable"}
        or text.startswith(WRITABLE_TYPE_PREFIXES)
        or any(token in text for token in WRITABLE_TYPE_TOKENS)
    )


def _load_writable_points(site_id: str) -> list[dict[str, Any]]:
    if os.environ.get("SUPABASE_SERVICE_ROLE_KEY"):
        from app.database.supabase_client import get_supabase_client  # noqa: PLC0415

        sb = get_supabase_client()
        site_resp = sb.table("sites").select("id").eq("code", site_id).limit(1).execute()
        if not site_resp.data:
            raise SystemExit(f"ERROR: site {site_id} not found")
        site_uuid = site_resp.data[0]["id"]

        rows = (
            sb.table("point_asset_mappings")
            .select("bms_point_id,extracted_asset_id,parameter_name,parameter_type")
            .eq("site_id", site_uuid)
            .eq("is_verified", True)
            .execute()
        )
        raw_points = rows.data or []
    else:
        import psycopg2  # noqa: PLC0415
        import psycopg2.extras  # noqa: PLC0415

        database_url = os.environ.get("DATABASE_URL_DIRECT") or os.environ.get("DATABASE_URL")
        if not database_url:
            raise SystemExit("ERROR: SUPABASE_SERVICE_ROLE_KEY or DATABASE_URL_DIRECT is required")
        try:
            conn = psycopg2.connect(database_url)
        except psycopg2.OperationalError:
            fallback_url = os.environ.get(
                "SENTINEL_LOCAL_DB_FALLBACK",
                "postgresql://postgres:postgres@127.0.0.1:55322/postgres",
            )
            conn = psycopg2.connect(fallback_url)
        with conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("select id from public.sites where code = %s limit 1", (site_id,))
                site_row = cur.fetchone()
                if not site_row:
                    raise SystemExit(f"ERROR: site {site_id} not found")
                cur.execute(
                    """
                    select bms_point_id, extracted_asset_id, parameter_name, parameter_type
                    from public.point_asset_mappings
                    where site_id = %s
                      and is_verified = true
                    """,
                    (site_row["id"],),
                )
                raw_points = [dict(row) for row in cur.fetchall()]

    points = [row for row in raw_points if row.get("bms_point_id") and _is_writable(row.get("parameter_type"))]
    return sorted(points, key=lambda r: (r.get("extracted_asset_id") or "", r.get("bms_point_id") or ""))


def main() -> int:
    parser = argparse.ArgumentParser(description="Export bridge_writable_points.json from verified Supabase mappings")
    parser.add_argument("--site-id", required=True, help="Site code, for example site-002 or S002")
    parser.add_argument("--output", required=True, help="Output JSON path")
    parser.add_argument(
        "--shape",
        choices=("list", "object"),
        default="list",
        help="JSON shape. Use list for the current bridge whitelist file.",
    )
    args = parser.parse_args()

    site_id = _site_code(args.site_id)
    points = _load_writable_points(site_id)
    object_ids = sorted({str(row["bms_point_id"]).strip() for row in points})
    if not object_ids:
        raise SystemExit(f"ERROR: no verified writable points found for {site_id}")

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    if args.shape == "object":
        payload: Any = {
            "site_id": site_id,
            "object_ids": object_ids,
            "count": len(object_ids),
        }
    else:
        payload = object_ids
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Exported {len(object_ids)} writable object_id(s) for {site_id} to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
