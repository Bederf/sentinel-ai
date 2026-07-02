#!/usr/bin/env python3
"""Reset fake site-005 for a controlled re-onboarding drill.

This is not the real-client removal workflow. Real removed sites must be
archived first and retained for the configured legal retention period.

Default mode is dry-run. Destructive execution requires:

    backend/venv/bin/python backend/scripts/reset_fake_site005.py \
        --execute --confirm-fake-site-reset site-005
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psycopg2
from psycopg2 import sql


REPO_ROOT = Path(__file__).resolve().parents[2]
SITE_CODE = "site-005"
SITE_LABELS = (SITE_CODE, "S005", "SITE-005")
EQUIPMENT_PREFIXES = ("S005", "SITE-005", "site-005")

DB_URL = os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:55322/postgres")

SITE_REGISTRY_PATH = REPO_ROOT / "backend" / "app" / "data" / "sites" / "_registry.json"
MODEL_REGISTRY_PATH = REPO_ROOT / "backend" / "ml" / "models" / "registry.json"
MODEL_ROOT = MODEL_REGISTRY_PATH.parent
TOMBSTONE_DIR = REPO_ROOT / "backend" / "app" / "data" / "site_reset_tombstones"
FILESYSTEM_TARGETS = (
    REPO_ROOT / "backend" / "app" / "data" / "sites" / SITE_CODE,
    REPO_ROOT / "backend" / "app" / "data" / "simulation" / "S005",
    REPO_ROOT / "backend" / "app" / "data" / "simulation" / SITE_CODE,
)


@dataclass(frozen=True)
class TableMatch:
    table: str
    count: int
    where_sql: sql.Composed
    params: list[Any]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Dry-run or execute the fake site-005 reset.")
    parser.add_argument("--execute", action="store_true", help="Actually delete S005 rows/files.")
    parser.add_argument(
        "--confirm-fake-site-reset",
        default="",
        help="Must be exactly site-005 when --execute is used.",
    )
    parser.add_argument("--database-url", default=DB_URL, help="Postgres connection URL.")
    return parser.parse_args()


def connect(database_url: str):
    return psycopg2.connect(database_url)


def fetch_site(conn) -> tuple[str, str] | None:
    with conn.cursor() as cur:
        cur.execute("select id::text, code from public.sites where code = %s", [SITE_CODE])
        row = cur.fetchone()
    return (row[0], row[1]) if row else None


def fetch_equipment(conn, site_uuid: str) -> list[tuple[str, str]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            select id::text, code
            from public.equipment
            where site_id = %s::uuid
               or code ilike any(%s)
            order by code
            """,
            [site_uuid, [f"{prefix}%" for prefix in EQUIPMENT_PREFIXES]],
        )
        return [(row[0], row[1]) for row in cur.fetchall()]


def fetch_public_base_tables(conn) -> dict[str, dict[str, str]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            select c.table_name, c.column_name, c.data_type
            from information_schema.columns c
            join information_schema.tables t
              on t.table_schema = c.table_schema
             and t.table_name = c.table_name
            where c.table_schema = 'public'
              and t.table_type = 'BASE TABLE'
            order by c.table_name, c.ordinal_position
            """
        )
        rows = cur.fetchall()

    tables: dict[str, dict[str, str]] = {}
    for table, column, data_type in rows:
        tables.setdefault(table, {})[column] = data_type
    return tables


def build_match_clause(
    table: str,
    columns: dict[str, str],
    site_uuid: str,
    equipment_ids: list[str],
    equipment_codes: list[str],
) -> tuple[sql.Composed, list[Any]] | None:
    clauses: list[sql.Composed] = []
    params: list[Any] = []

    text_site_columns = ("site_id", "site_code", "building_id", "site")
    text_equipment_columns = ("equipment_id", "equipment_code", "target_equipment")

    for column in text_site_columns:
        data_type = columns.get(column)
        if data_type in {"text", "character varying", "character"}:
            clauses.append(sql.SQL("{} = any(%s)").format(sql.Identifier(column)))
            params.append(list(SITE_LABELS))
        elif column == "site_id" and data_type == "uuid":
            clauses.append(sql.SQL("{} = %s::uuid").format(sql.Identifier(column)))
            params.append(site_uuid)

    for column in text_equipment_columns:
        data_type = columns.get(column)
        if data_type == "uuid" and equipment_ids:
            clauses.append(sql.SQL("{} = any(%s::uuid[])").format(sql.Identifier(column)))
            params.append(equipment_ids)
        elif data_type in {"text", "character varying", "character"}:
            clauses.append(
                sql.SQL("({} ilike any(%s) or {} = any(%s))").format(sql.Identifier(column), sql.Identifier(column))
            )
            params.append([f"{prefix}%" for prefix in EQUIPMENT_PREFIXES])
            params.append(equipment_codes)

    if table == "sites" and columns.get("code") in {"text", "character varying", "character"}:
        clauses.append(sql.SQL("{} = %s").format(sql.Identifier("code")))
        params.append(SITE_CODE)

    if table == "equipment" and columns.get("code") in {"text", "character varying", "character"}:
        clauses.append(sql.SQL("{} ilike any(%s)").format(sql.Identifier("code")))
        params.append([f"{prefix}%" for prefix in EQUIPMENT_PREFIXES])

    if not clauses:
        return None

    return sql.SQL(" or ").join(clauses), params


def discover_table_matches(conn, site_uuid: str, equipment: list[tuple[str, str]]) -> list[TableMatch]:
    equipment_ids = [row[0] for row in equipment]
    equipment_codes = [row[1] for row in equipment if row[1]]
    matches: list[TableMatch] = []

    for table, columns in fetch_public_base_tables(conn).items():
        clause = build_match_clause(table, columns, site_uuid, equipment_ids, equipment_codes)
        if not clause:
            continue
        where_sql, params = clause
        query = sql.SQL("select count(*) from public.{} where ").format(sql.Identifier(table)) + where_sql
        with conn.cursor() as cur:
            cur.execute(query, params)
            count = int(cur.fetchone()[0])
        if count:
            matches.append(TableMatch(table=table, count=count, where_sql=where_sql, params=params))

    return matches


def fetch_fk_edges(conn, tables: set[str]) -> set[tuple[str, str]]:
    if not tables:
        return set()
    with conn.cursor() as cur:
        cur.execute(
            """
            select tc.table_name as child_table, ccu.table_name as parent_table
            from information_schema.table_constraints tc
            join information_schema.constraint_column_usage ccu
              on ccu.constraint_name = tc.constraint_name
             and ccu.constraint_schema = tc.constraint_schema
            where tc.table_schema = 'public'
              and tc.constraint_type = 'FOREIGN KEY'
              and tc.table_name = any(%s)
              and ccu.table_name = any(%s)
            """,
            [list(tables), list(tables)],
        )
        return {(child, parent) for child, parent in cur.fetchall() if child != parent}


def order_for_delete(conn, matches: list[TableMatch]) -> list[TableMatch]:
    by_table = {match.table: match for match in matches}
    tables = set(by_table)
    edges = fetch_fk_edges(conn, tables)

    # Add conservative parent ordering for text-only relationships that are not
    # declared as foreign keys.
    for table in list(tables):
        if table not in {"sites", "equipment"}:
            if "sites" in tables:
                edges.add((table, "sites"))
            if "equipment" in tables:
                edges.add((table, "equipment"))
    if "equipment" in tables and "sites" in tables:
        edges.add(("equipment", "sites"))

    children_for: dict[str, set[str]] = {table: set() for table in tables}
    parent_count: dict[str, int] = dict.fromkeys(tables, 0)
    for child, parent in edges:
        if child not in tables or parent not in tables:
            continue
        children_for[child].add(parent)
        parent_count[parent] += 1

    ready = sorted(table for table, count in parent_count.items() if count == 0)
    ordered: list[str] = []
    while ready:
        table = ready.pop(0)
        ordered.append(table)
        for parent in sorted(children_for[table]):
            parent_count[parent] -= 1
            if parent_count[parent] == 0:
                ready.append(parent)
        ready.sort()

    if len(ordered) != len(tables):
        remaining = sorted(tables - set(ordered))
        ordered.extend(remaining)

    return [by_table[table] for table in ordered]


def delete_db_rows(conn, ordered_matches: list[TableMatch]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    with conn.cursor() as cur:
        for match in ordered_matches:
            query = sql.SQL("delete from public.{} where ").format(sql.Identifier(match.table)) + match.where_sql
            cur.execute(query, match.params)
            results.append({"table": match.table, "deleted_rows": cur.rowcount})
    return results


def scan_site_registry() -> dict[str, Any]:
    if not SITE_REGISTRY_PATH.exists():
        return {"path": str(SITE_REGISTRY_PATH), "exists": False}
    data = json.loads(SITE_REGISTRY_PATH.read_text())
    return {
        "path": str(SITE_REGISTRY_PATH),
        "exists": True,
        "active_contains_site": SITE_CODE in data.get("active_sites", []),
        "inactive_contains_site": SITE_CODE in data.get("inactive_sites", []),
    }


def update_site_registry(execute: bool) -> dict[str, Any]:
    state = scan_site_registry()
    if not execute or not state.get("exists"):
        return state

    data = json.loads(SITE_REGISTRY_PATH.read_text())
    for key in ("active_sites", "inactive_sites"):
        if isinstance(data.get(key), list):
            data[key] = [site for site in data[key] if site != SITE_CODE]
    SITE_REGISTRY_PATH.write_text(json.dumps(data, indent=2) + "\n")
    state["updated"] = True
    return state


def scan_filesystem_targets() -> list[dict[str, Any]]:
    targets: list[dict[str, Any]] = []
    for path in FILESYSTEM_TARGETS:
        if path.exists():
            if path.is_dir():
                file_count = sum(1 for child in path.rglob("*") if child.is_file())
            else:
                file_count = 1
            targets.append({"path": str(path), "exists": True, "file_count": file_count})
        else:
            targets.append({"path": str(path), "exists": False, "file_count": 0})
    return targets


def remove_filesystem_targets(execute: bool) -> list[dict[str, Any]]:
    targets = scan_filesystem_targets()
    if not execute:
        return targets
    for target in targets:
        path = Path(target["path"])
        if not path.exists():
            continue
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
        target["removed"] = True
    return targets


def _entry_site_id(entry: dict[str, Any]) -> str | None:
    raw_metadata = entry.get("metadata")
    metadata: dict[str, Any] = raw_metadata if isinstance(raw_metadata, dict) else {}
    return entry.get("site_id") or metadata.get("site_id")


def _model_files_for_entry(entry: dict[str, Any]) -> list[Path]:
    paths: list[Path] = []
    raw_metadata = entry.get("metadata")
    metadata: dict[str, Any] = raw_metadata if isinstance(raw_metadata, dict) else {}
    for key in ("model_path",):
        value = entry.get(key)
        if value:
            paths.append(MODEL_ROOT / value)
    for key in ("scaler_path", "threshold_path"):
        value = metadata.get(key)
        if value:
            paths.append(MODEL_ROOT / value)

    model_path = entry.get("model_path")
    if model_path:
        path = MODEL_ROOT / model_path
        paths.append(path.with_name(f"{path.stem}_threshold.npy"))
        paths.append(path.with_name(f"{path.stem}_scaler.joblib"))
    return sorted(set(paths))


def scan_model_registry() -> dict[str, Any]:
    if not MODEL_REGISTRY_PATH.exists():
        return {"path": str(MODEL_REGISTRY_PATH), "exists": False, "entries": []}

    data = json.loads(MODEL_REGISTRY_PATH.read_text())
    entries = []
    for model_id, entry in sorted((data.get("models") or {}).items()):
        if _entry_site_id(entry) != SITE_CODE:
            continue
        model_files = _model_files_for_entry(entry)
        entries.append(
            {
                "model_id": model_id,
                "status": entry.get("status"),
                "model_type": entry.get("model_type"),
                "equipment_type": entry.get("equipment_type"),
                "files": [{"path": str(path), "exists": path.exists()} for path in model_files],
            }
        )

    active_refs = {
        key: value
        for key, value in (data.get("active") or {}).items()
        if value in {entry["model_id"] for entry in entries} or SITE_CODE in key
    }
    return {
        "path": str(MODEL_REGISTRY_PATH),
        "exists": True,
        "entries": entries,
        "active_refs": active_refs,
    }


def update_model_registry(execute: bool) -> dict[str, Any]:
    state = scan_model_registry()
    if not execute or not state.get("exists"):
        return state

    data = json.loads(MODEL_REGISTRY_PATH.read_text())
    remove_ids = {entry["model_id"] for entry in state["entries"]}
    for model_id in remove_ids:
        data.get("models", {}).pop(model_id, None)
    for active_key, model_id in list((data.get("active") or {}).items()):
        if model_id in remove_ids or SITE_CODE in active_key:
            data["active"].pop(active_key, None)

    removed_files = []
    for entry in state["entries"]:
        for file_info in entry["files"]:
            path = Path(file_info["path"])
            if path.exists():
                path.unlink()
                removed_files.append(str(path))

    MODEL_REGISTRY_PATH.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    state["removed_model_ids"] = sorted(remove_ids)
    state["removed_files"] = sorted(removed_files)
    return state


def write_tombstone(report: dict[str, Any], execute: bool) -> str | None:
    if not execute:
        return None
    TOMBSTONE_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = TOMBSTONE_DIR / f"{SITE_CODE}-reset-{stamp}.json"
    tombstone = {
        "site_code": SITE_CODE,
        "reset_type": "fake_site_purge_for_reonboarding_drill",
        "real_client_site_policy": "archive_first_10_year_retention_required",
        "created_at": datetime.now(UTC).isoformat(),
        "report": report,
    }
    path.write_text(json.dumps(tombstone, indent=2, sort_keys=True) + "\n")
    return str(path)


def build_report(conn, execute: bool) -> dict[str, Any]:
    site = fetch_site(conn)
    if not site:
        site_uuid = None
        equipment: list[tuple[str, str]] = []
        matches: list[TableMatch] = []
        ordered_matches: list[TableMatch] = []
    else:
        site_uuid = site[0]
        equipment = fetch_equipment(conn, site_uuid)
        matches = discover_table_matches(conn, site_uuid, equipment)
        ordered_matches = order_for_delete(conn, matches)

    report = {
        "mode": "execute" if execute else "dry_run",
        "site_code": SITE_CODE,
        "site_uuid": site_uuid,
        "equipment_count": len(equipment),
        "equipment_sample": [code for _, code in equipment[:20]],
        "db_matches": [
            {"table": match.table, "rows": match.count} for match in sorted(matches, key=lambda item: item.table)
        ],
        "db_delete_order": [{"table": match.table, "rows": match.count} for match in ordered_matches],
        "site_registry": scan_site_registry(),
        "filesystem_targets": scan_filesystem_targets(),
        "model_registry": scan_model_registry(),
    }

    if execute and site_uuid:
        report["db_delete_results"] = delete_db_rows(conn, ordered_matches)
        report["site_registry"] = update_site_registry(execute=True)
        report["filesystem_targets"] = remove_filesystem_targets(execute=True)
        report["model_registry"] = update_model_registry(execute=True)

    return report


def main() -> int:
    args = parse_args()
    if args.execute and args.confirm_fake_site_reset != SITE_CODE:
        print("ERROR: --execute requires --confirm-fake-site-reset site-005", file=sys.stderr)
        return 2

    with connect(args.database_url) as conn:
        conn.autocommit = False
        report = build_report(conn, execute=args.execute)
        if args.execute:
            tombstone_path = write_tombstone(report, execute=True)
            report["tombstone_path"] = tombstone_path
            conn.commit()
        else:
            conn.rollback()

    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
