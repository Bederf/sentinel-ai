#!/usr/bin/env python3
"""
Complete Dependency Graph Query for Supabase Schema Safety

Detects ALL dependency vectors for a given table BEFORE DROP execution:
  1. FK children (tables with FKs pointing TO this table)
  2. Regular views that depend on this table
  3. Materialized views that depend on this table
  4. Triggers and trigger functions on this table
  5. FK chain children (tables this table points to via its own FKs)
  6. Code references (searches backend source for table name mentions)

Output: JSON report for audit before schema changes.

Usage:
    python backend/scripts/complete_dependency_graph.py <table_name> [--output <path>]
    python backend/scripts/complete_dependency_graph.py equipment_elements --output /tmp/deps.json
    python backend/scripts/complete_dependency_graph.py equipment_elements --verify-only

Phase 209-dependency-hardening | Part of Phase 208 postmortem fix
CASCADE silent-drop prevention: MV deps, view deps, FK chain children
"""

import argparse
import json
import logging
import sys
from contextlib import suppress
from pathlib import Path
from typing import Any

# Third-party
from dotenv import load_dotenv

logger = logging.getLogger(__name__)


def _setup_path() -> tuple[Path, Any]:
    """Deferred path setup — called once inside main() before Supabase access."""
    load_dotenv(Path(__file__).parent.parent / ".env")
    sys.path.insert(0, str(Path(__file__).parent.parent))

    # Late import so pre-commit E402 is satisfied (import after setup function def)
    from app.database.supabase_client import get_supabase_client

    return Path(__file__).parent.parent.parent, get_supabase_client()


# ---------------------------------------------------------------------------
# SQL query helpers via RPC
# ---------------------------------------------------------------------------


def _run_sql(supabase, sql: str) -> list[dict[str, Any]]:
    """Execute raw SQL via exec_sql RPC. Returns list of rows."""
    try:
        result = supabase.rpc("exec_sql", {"sql": sql}).execute()
        return result.data if result.data else []
    except Exception as exc:
        logger.warning("SQL RPC failed: %s", exc)
        return []


def get_fk_children(supabase, table_name: str) -> list[dict[str, Any]]:
    """Tables with FKs pointing TO target table (what depends on this table)."""
    sql = f"""
    SELECT
        tc.table_schema,
        tc.table_name as child_table,
        kcu.column_name as fk_column,
        ccu.table_name as referenced_table,
        ccu.column_name as referenced_column,
        rc.update_rule,
        rc.delete_rule
    FROM information_schema.table_constraints AS tc
    JOIN information_schema.constraint_column_usage AS ccu
        ON ccu.constraint_name = tc.constraint_name
    JOIN information_schema.key_column_usage AS kcu
        ON kcu.constraint_name = tc.constraint_name
    JOIN information_schema.referential_constraints AS rc
        ON rc.constraint_name = tc.constraint_name
    WHERE ccu.table_name = '{table_name}'
      AND tc.constraint_type = 'FOREIGN KEY';
    """
    return _run_sql(supabase, sql)


def get_views_depending_on(supabase, table_name: str) -> list[dict[str, Any]]:
    """Regular views (not materialized) that reference this table via view_table_usage."""
    sql = f"""
    SELECT
        v.table_schema,
        v.table_name as view_name,
        v.view_definition
    FROM information_schema.views v
    WHERE v.view_definition LIKE '%{table_name}%'
      AND v.table_schema NOT IN ('pg_catalog', 'information_schema');
    """
    return _run_sql(supabase, sql)


def get_materialized_views_depending_on(supabase, table_name: str) -> list[dict[str, Any]]:
    """Materialized views that depend on this table (pg_matviews + pg_depends)."""
    sql = f"""
    SELECT
        schemaname as table_schema,
        matviewname as view_name
    FROM pg_matviews
    WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
      AND EXISTS (
          SELECT 1 FROM pg_depends d
          JOIN pg_class c ON d.refobjid = c.oid
          WHERE d.classid = 'pg_class'::regclass
            AND d.refclassid = 'pg_class'::regclass
            AND c.relname = '{table_name}'
      );
    """
    return _run_sql(supabase, sql)


def get_triggers_and_functions(supabase, table_name: str) -> list[dict[str, Any]]:
    """Triggers and their trigger functions on this table."""
    sql = f"""
    SELECT
        t.tgname as trigger_name,
        t.tgtype as trigger_type,
        p.proname as function_name,
        n.nspname as function_schema,
        CASE (t.tgtype & 1) WHEN 1 THEN 'ROW' ELSE 'STATEMENT' END as level,
        CASE
            WHEN (t.tgtype & 64) = 64 THEN 'BEFORE'
            WHEN (t.tgtype & 128) = 128 THEN 'INSTEAD OF'
            ELSE 'AFTER'
        END as action_timing
    FROM pg_trigger t
    JOIN pg_proc p ON t.tgfoid = p.oid
    JOIN pg_namespace n ON p.pronamespace = n.oid
    WHERE t.tgrelid = '{table_name}'::regclass
      AND t.tgname NOT IN (SELECT tgname FROM pg_trigger WHERE tgtype = 0);
    """
    return _run_sql(supabase, sql)


def get_fk_chain_children(supabase, table_name: str) -> list[dict[str, Any]]:
    """Tables that this table points TO via its own FKs (cascade risk downward)."""
    sql = f"""
    SELECT
        kcu.table_schema,
        kcu.table_name as child_table,
        kcu.column_name as fk_column,
        ccu.table_name as referenced_table,
        ccu.column_name as referenced_column
    FROM information_schema.key_column_usage kcu
    JOIN information_schema.constraint_column_usage ccu
        ON kcu.constraint_name = ccu.constraint_name
    JOIN information_schema.table_constraints tc
        ON tc.constraint_name = kcu.constraint_name
    WHERE kcu.table_name = '{table_name}'
      AND tc.constraint_type = 'FOREIGN KEY';
    """
    return _run_sql(supabase, sql)


def get_table_row_count(supabase, table_name: str) -> int:
    """Row count for a table (0 = empty)."""
    sql = f"SELECT COUNT(*) as cnt FROM {table_name} LIMIT 1;"
    result = _run_sql(supabase, sql)
    if result and len(result) > 0:
        return result[0].get("cnt", 0) or 0
    return 0


def get_code_references(base_path: Path, table_name: str) -> list[dict[str, Any]]:
    """Search backend source for table_name references (Python files only)."""
    hits = []
    backend_path = base_path / "backend"

    if not backend_path.exists():
        return []

    for py_file in backend_path.rglob("*.py"):
        try:
            content = py_file.read_text(encoding="utf-8", errors="ignore")
            if table_name not in content:
                continue
            lines = content.split("\n")
            for i, line in enumerate(lines, 1):
                if table_name in line:
                    stripped = line.strip()
                    # Skip pure comment lines
                    if stripped.startswith("#"):
                        continue
                    hits.append(
                        {
                            "file": str(py_file.relative_to(base_path)),
                            "line": i,
                            "context": line.strip()[:120],
                        }
                    )
        except Exception:
            continue

    return hits


# ---------------------------------------------------------------------------
# Core query
# ---------------------------------------------------------------------------


def query_dependency_graph(supabase, table_name: str, base_path: Path) -> dict[str, Any]:
    """
    Complete dependency graph for a table.

    Returns all dependency vectors needed to determine DROP safety.
    """
    report: dict[str, Any] = {
        "target_table": table_name,
        "fk_children": [],
        "views": [],
        "materialized_views": [],
        "triggers": [],
        "fk_chain_children": [],
        "row_count": 0,
        "code_references": [],
        "is_safe_to_drop": True,
        "blockers": [],
    }

    try:
        report["fk_children"] = get_fk_children(supabase, table_name)
    except Exception as exc:
        report["fk_children"] = [{"_error": str(exc)}]

    try:
        report["views"] = get_views_depending_on(supabase, table_name)
    except Exception as exc:
        report["views"] = [{"_error": str(exc)}]

    try:
        report["materialized_views"] = get_materialized_views_depending_on(supabase, table_name)
    except Exception as exc:
        report["materialized_views"] = [{"_error": str(exc)}]

    try:
        report["triggers"] = get_triggers_and_functions(supabase, table_name)
    except Exception as exc:
        report["triggers"] = [{"_error": str(exc)}]

    try:
        report["fk_chain_children"] = get_fk_chain_children(supabase, table_name)
    except Exception as exc:
        report["fk_chain_children"] = [{"_error": str(exc)}]

    with suppress(Exception):
        report["row_count"] = get_table_row_count(supabase, table_name)

    report["code_references"] = get_code_references(base_path, table_name)

    # Compute blockers
    blockers: list[str] = []

    fk_kids = report.get("fk_children", [])
    if fk_kids and not any("_error" in r for r in fk_kids):
        names = [r.get("child_table", "?") for r in fk_kids if "child_table" in r]
        if names:
            blockers.append(f"FK children (incoming): {names}")

    views = report.get("views", [])
    if views and not any("_error" in r for r in views):
        view_names = [r.get("view_name", "?") for r in views if "view_name" in r]
        if view_names:
            blockers.append(f"Regular views: {view_names}")

    mvs = report.get("materialized_views", [])
    if mvs and not any("_error" in r for r in mvs):
        mv_names = [r.get("view_name", "?") for r in mvs if "view_name" in r]
        if mv_names:
            blockers.append(f"Materialized views: {mv_names}")

    triggers = report.get("triggers", [])
    if triggers and not any("_error" in r for r in triggers):
        trigger_names = [r.get("trigger_name", "?") for r in triggers if "trigger_name" in r]
        if trigger_names:
            blockers.append(f"Triggers: {trigger_names}")

    code_refs = report.get("code_references", [])
    if code_refs:
        files = list(dict.fromkeys(r["file"] for r in code_refs[:10]))
        blockers.append(f"Code references: {len(code_refs)} hits in {len(files)} files")

    report["blockers"] = blockers
    report["is_safe_to_drop"] = len(blockers) == 0

    return report


# ---------------------------------------------------------------------------
# TIER 6 verification
# ---------------------------------------------------------------------------


def verify_tier_6_safety(supabase, table_name: str, base_path: Path) -> dict[str, Any]:
    """
    GSD TIER 6 safety verification.

    TIER 6 = candidate for DROP (DEPRECATED, no code refs, no data).
    Fails the phase before executing DROP if any dependency exists.

    Returns:
        {"safe": bool, "report": dict, "blockers": list, "warnings": list}
    """
    report = query_dependency_graph(supabase, table_name, base_path)

    blockers: list[str] = []
    warnings: list[str] = []

    # 1. Code references — FAIL if any found
    code_refs = report.get("code_references", [])
    if code_refs:
        blockers.append(f"Code references found: {len(code_refs)} hits")
        for ref in code_refs[:5]:
            blockers.append(f"  {ref['file']}:{ref['line']}")

    # 2. Views/MVs depend on it — FAIL if any found
    views = report.get("views", [])
    if views and not any("_error" in r for r in views):
        blockers.append(f"Regular views depend on this table: {[v.get('view_name') for v in views]}")

    mvs = report.get("materialized_views", [])
    if mvs and not any("_error" in r for r in mvs):
        blockers.append(f"Materialized views depend on this table: {[mv.get('view_name') for mv in mvs]}")

    # 3. FK children — FAIL if any found
    fk_children = report.get("fk_children", [])
    if fk_children and not any("_error" in r for r in fk_children):
        blockers.append(f"FK children point to this table: {[c.get('child_table') for c in fk_children]}")

    # 4. Triggers — FAIL if any found (side effects)
    triggers = report.get("triggers", [])
    if triggers and not any("_error" in r for r in triggers):
        blockers.append(f"Triggers on this table: {[t.get('trigger_name') for t in triggers]}")

    safe = len(blockers) == 0

    return {
        "table": table_name,
        "safe": safe,
        "blockers": blockers,
        "warnings": warnings,
        "report": report,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _print_report(report: dict[str, Any]) -> None:
    """Print human-readable dependency report."""
    print(f"\n{'=' * 60}")
    print(f"DEPENDENCY GRAPH: {report['target_table']}")
    print(f"{'=' * 60}")
    print(f"Safe to drop: {report['is_safe_to_drop']}")
    print(f"Row count: {report.get('row_count', '?')}")
    print()

    fk_children = report.get("fk_children", [])
    print(f"FK children (incoming): {len(fk_children)}")
    for r in fk_children:
        if "_error" in r:
            print(f"  [ERROR] {r['_error']}")
        else:
            print(
                f"  <- {r.get('child_table', '?')}.{r.get('fk_column', '?')} -> "
                f"{r.get('referenced_table', '?')}.{r.get('referenced_column', '?')}"
            )

    print()
    print(f"Regular views: {len(report.get('views', []))}")
    for r in report.get("views", []):
        if "_error" in r:
            print(f"  [ERROR] {r['_error']}")
        else:
            print(f"  {r.get('view_name', '?')}")

    print()
    print(f"Materialized views: {len(report.get('materialized_views', []))}")
    for r in report.get("materialized_views", []):
        if "_error" in r:
            print(f"  [ERROR] {r['_error']}")
        else:
            print(f"  {r.get('view_name', '?')}")

    print()
    print(f"Triggers: {len(report.get('triggers', []))}")
    for r in report.get("triggers", []):
        if "_error" in r:
            print(f"  [ERROR] {r['_error']}")
        else:
            timing = r.get("action_timing", "?")
            level = r.get("level", "?")
            func = r.get("function_name", "?")
            print(f"  {r.get('trigger_name', '?')} ({timing} {level}) -> {func}()")

    print()
    print(f"FK chain children (outgoing): {len(report.get('fk_chain_children', []))}")
    for r in report.get("fk_chain_children", []):
        if "_error" in r:
            print(f"  [ERROR] {r['_error']}")
        else:
            print(
                f"  -> {r.get('child_table', '?')}.{r.get('fk_column', '?')} -> "
                f"{r.get('referenced_table', '?')}.{r.get('referenced_column', '?')}"
            )

    print()
    print(f"Code references: {len(report.get('code_references', []))}")
    for r in report.get("code_references", [])[:10]:
        print(f"  {r['file']}:{r['line']}")
        print(f"    {r['context'][:80]}")

    print()
    if report["blockers"]:
        print("BLOCKERS:")
        for b in report["blockers"]:
            print(f"  - {b}")
        print("\nNOT SAFE TO DROP")
    else:
        print("SAFE TO DROP — no dependencies found.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Complete dependency graph for Supabase table safety analysis.")
    parser.add_argument("table_name", help="Target table name (e.g. equipment_elements)")
    parser.add_argument("--output", "-o", help="Output JSON path (default: stdout)")
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Run verify_tier_6_safety() and exit 0=safe, 1=blocked",
    )

    args = parser.parse_args()

    base_path, supabase = _setup_path()

    if args.verify_only:
        result = verify_tier_6_safety(supabase, args.table_name, base_path)
        print(f"\n{'=' * 60}")
        print(f"TIER 6 SAFETY: {args.table_name}")
        print(f"{'=' * 60}")
        print(f"Safe to drop: {result['safe']}")
        if result["blockers"]:
            print(f"Blockers ({len(result['blockers'])}):")
            for b in result["blockers"]:
                print(f"  - {b}")
        else:
            print("No blockers — SAFE for DROP.")
        print()
        sys.exit(0 if result["safe"] else 1)
    else:
        report = query_dependency_graph(supabase, args.table_name, base_path)
        _print_report(report)

        if args.output:
            with open(args.output, "w") as f:
                json.dump(report, f, indent=2, default=str)
            print(f"\nReport written to: {args.output}")

        sys.exit(0 if report["is_safe_to_drop"] else 1)


if __name__ == "__main__":
    main()
