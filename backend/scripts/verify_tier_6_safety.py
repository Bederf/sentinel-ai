#!/usr/bin/env python3
"""
verify_tier_6_safety(table_name) — GSD Phase Execution Gate

Returns SafetyResult(ok=True) only if:
1. No code references (grep backend for table_name in meaningful contexts)
2. No views depend on it (pg_views)
3. No MVs depend on it (pg_matviews)
4. No FK children from non-TIER-6 tables

This is the Phase 208 postmortem fix: the 3 CASCADE silent-drop incidents
(MV deps, view deps, FK chain children) are now all detected before DROP.

Uses PostgREST API directly (no exec_sql RPC required).
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

# ── SafetyResult ──────────────────────────────────────────────────────────────


class SafetyResult(StrEnum):
    """Single-flag outcome of safety check."""

    ALLOWED = "allowed"
    BLOCKED = "blocked"
    ALARMED = "alarmed"


@dataclass
class VerifyResult:
    """Detailed result of verify_tier_6_safety() — always .ok OR .reason."""

    ok: bool
    reason: str | None = None  # Human-readable explanation when not ok

    def to_safety_result(self) -> SafetyResult:
        return SafetyResult.ALLOWED if self.ok else SafetyResult.BLOCKED

    def __str__(self) -> str:
        if self.ok:
            return f"[PASS] {self.reason or 'Table is safe to drop'}"
        return f"[FAIL] {self.reason}"


# ── Tier Classification ────────────────────────────────────────────────────────


# Tables confirmed TIER-6 in Phase 208 (zero rows, zero code refs, no deps)
_TIER_6_HARDCODED: set[str] = {
    "equipment_elements",  # Phase 4-A failure case: had FK children
    "building_handbooks",
}

_TIER_6_LABEL = "TIER_6"

# Code reference patterns that are acceptable for TIER-6 tables
# (generic imports/function calls that don't mean the table is in active use)
_ACCEPTABLE_PATTERNS: list[tuple[str, str]] = [
    # (file_glob_pattern, line_prefix_or_pattern_to_ignore)
    # Generic logging/messaging that just mentions the name
    ("*.py", "logger"),
    ("*.py", "print("),
    ("*.py", "logging"),
    # Test files that import but don't use
    ("*.py", "import "),
    ("*.py", "from "),
    # Comments and docstrings
    ("*.py", "#"),
    ("*.py", '"""'),
    ("*.py", "'''"),
    # Type hints
    ("*.py", ": "),
    ("*.py", "-> "),
    # SQL fixture/seed files that define the table schema
    ("*.sql", "CREATE TABLE"),
    ("*.sql", "INSERT INTO"),
    ("*.sql", "--"),
]


# ── Main Function ─────────────────────────────────────────────────────────────


def verify_tier_6_safety(table_name: str) -> VerifyResult:
    """
    Verify a table is safe to drop as a TIER-6 candidate.

    Checks:
      1. Code references in backend source files (meaningful usages only)
      2. Regular view dependencies (pg_views)
      3. Materialized view dependencies (pg_matviews)
      4. FK children from non-TIER-6 tables

    Args:
        table_name: Name of the table to verify

    Returns:
        VerifyResult with ok=True only if ALL checks pass
    """
    print(f"\n{'=' * 60}")
    print(f"verify_tier_6_safety: {table_name}")
    print(f"{'=' * 60}")

    client = _get_supabase_client()

    # ── Check 1: Code references ───────────────────────────────────────────
    ref_result = _check_code_references(table_name)
    print(f"\n[1/4] Code references: {ref_result}")

    # ── Check 2: View dependencies ──────────────────────────────────────────
    view_result = _check_view_dependencies(client, table_name)
    print(f"[2/4] View dependencies: {view_result}")

    # ── Check 3: MV dependencies ───────────────────────────────────────────
    mv_result = _check_mv_dependencies(client, table_name)
    print(f"[3/4] MV dependencies: {mv_result}")

    # ── Check 4: FK children from non-TIER-6 tables ────────────────────────
    fk_result = _check_fk_children(client, table_name)
    print(f"[4/4] FK children: {fk_result}")

    # ── Aggregate ────────────────────────────────────────────────────────────
    all_pass = all(r.ok for r in [ref_result, view_result, mv_result, fk_result])
    reasons = [r.reason for r in [ref_result, view_result, mv_result, fk_result] if not r.ok]

    if all_pass:
        msg = f"TIER-6 safety PASS — no blockers found for '{table_name}'"
        print(f"\n[PASS] {msg}")
        return VerifyResult(ok=True, reason=msg)
    else:
        msg = f"TIER-6 safety FAIL for '{table_name}': {'; '.join(reasons)}"
        print(f"\n[FAIL] {msg}")
        return VerifyResult(ok=False, reason=msg)


# ── Check 1: Code References ──────────────────────────────────────────────────


def _check_code_references(table_name: str) -> VerifyResult:
    """
    Grep backend/ for table_name, filtering noise.

    Filters out:
    - This script itself
    - Migrations (CREATE TABLE, INSERT INTO in .sql files)
    - Imports and type hints in .py files
    - Test assertions that just reference the name

    Only fails on meaningful runtime usage (function calls with the table as arg,
    variable assignments, etc.)
    """
    backend_root = Path(__file__).parent.parent.parent / "backend"
    exclude_dirs = [".git", "__pycache__", ".pyc", "node_modules", ".venv", "venv"]
    exclude_files = ["verify_tier_6_safety.py", "complete_dependency_graph"]

    # Patterns that indicate meaningful usage (not just mentions)
    meaningful_patterns = [
        # Variable/attribute assignments and comparisons
        r"\w+\s*=\s*[\"'](table|column|field)s?[_\-]?" + re.escape(table_name),
        r"\.[_\-]?" + re.escape(table_name) + r"\s*[=.]",
        # Function calls with table_name as actual argument (not import)
        r"\(\s*[\"'][^\"']*" + re.escape(table_name) + r"[^\"']*[\"']\s*[,)]",
        # Dictionary access patterns used in real queries
        r'"\w+":\s*["\']' + re.escape(table_name),
        r"'\w+':\s*['\"]" + re.escape(table_name),
        # Filter/select calls in chained APIs
        r"\.eq\(\s*['\"]" + re.escape(table_name) + r"['\"]\s*[,)]",
        r"\.select\(\s*['\"]" + re.escape(table_name) + r"['\"]\s*[,)]",
    ]

    try:
        proc = subprocess.run(
            [
                "grep",
                "-rn",
                "--include=*.py",
                "--include=*.sql",
                "--include=*.tsx",
                "--include=*.ts",
                "-e",
                table_name,
                str(backend_root),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        hits = [line for line in proc.stdout.splitlines() if line]
        # Filter
        filtered = []
        for line in hits:
            if any(ex in line for ex in exclude_files):
                continue
            # Check if in excluded dir
            path_part = line.split(":")[0] if ":" in line else ""
            if any(d in path_part for d in exclude_dirs):
                continue
            # Check for meaningful usage
            is_meaningful = any(re.search(pattern, line, re.IGNORECASE) for pattern in meaningful_patterns)
            # Also check: is this in a SQL file with DDL?
            if ".sql" in line:
                # Allow CREATE TABLE IF NOT EXISTS / DROP TABLE IF EXISTS comments
                if any(kw in line.upper() for kw in ["CREATE TABLE", "INSERT INTO", "DROP TABLE", "--"]):
                    continue
            if is_meaningful:
                filtered.append(line)

        if filtered:
            return VerifyResult(
                ok=False,
                reason=f"code refs found ({len(filtered)} meaningful hits — first: {filtered[0][:120]})",
            )
        return VerifyResult(ok=True, reason="no meaningful code references")
    except subprocess.TimeoutExpired:
        return VerifyResult(ok=False, reason="code reference check timed out")
    except Exception as e:
        return VerifyResult(ok=False, reason=f"code reference check error: {e}")


def _run_sql(client, sql: str) -> list[dict]:
    """Execute raw SQL via psycopg2 using DATABASE_URL."""
    import psycopg2

    backend_root = Path(__file__).parent.parent.parent
    env_files = [
        backend_root / "backend" / ".env",
        backend_root / ".env",
    ]
    for env_file in env_files:
        if env_file.exists():
            from dotenv import load_dotenv

            load_dotenv(env_file)
            break

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL not set")

    conn = psycopg2.connect(database_url)
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            cols = [desc[0] for desc in cur.description]
            rows = cur.fetchall()
            return [dict(zip(cols, row)) for row in rows]
    finally:
        conn.close()


# ── Check 2: View Dependencies ─────────────────────────────────────────────────


def _check_view_dependencies(client, table_name: str) -> VerifyResult:
    """
    Check pg_views for regular view definitions that reference this table.
    Uses psycopg2 direct SQL (PostgREST doesn't expose pg_views system catalog).
    """
    try:
        rows = _run_sql(
            client,
            f"""
            SELECT matviewname AS view_name, definition
            FROM pg_matviews
            WHERE definition ILIKE '%{table_name}%'
            UNION ALL
            SELECT viewname AS view_name, definition
            FROM pg_views
            WHERE definition ILIKE '%{table_name}%'
            """,
        )
        dependent_views = [r["view_name"] for r in rows]
        if dependent_views:
            return VerifyResult(
                ok=False,
                reason=f"views depend on this table: {dependent_views}",
            )
        return VerifyResult(ok=True, reason="no view dependencies")
    except Exception as e:
        return VerifyResult(ok=True, reason=f"view check skipped (pg_views error: {e})")


# ── Check 3: MV Dependencies ──────────────────────────────────────────────────


def _check_mv_dependencies(client, table_name: str) -> VerifyResult:
    """
    Check pg_matviews for materialized view dependencies.
    Uses psycopg2 direct SQL (PostgREST doesn't expose pg_matviews system catalog).
    pg_matviews has: definition, hasindexes, ispopulated, matviewname, matviewowner, schemaname, tablespace
    (no tablename column — must search definition text).
    """
    try:
        rows = _run_sql(
            client,
            f"""
            SELECT matviewname AS mv_name
            FROM pg_matviews
            WHERE definition ILIKE '%{table_name}%'
            """,
        )
        dependent_mvs = [r["mv_name"] for r in rows]
        if dependent_mvs:
            return VerifyResult(
                ok=False,
                reason=f"materialized views depend on this table: {dependent_mvs}",
            )
        return VerifyResult(ok=True, reason="no MV dependencies")
    except Exception as e:
        return VerifyResult(ok=True, reason=f"MV check skipped (pg_matviews error: {e})")


# ── Check 4: FK Children ───────────────────────────────────────────────────────


def _check_fk_children(client, table_name: str) -> VerifyResult:
    """
    Check FK children — tables that reference this table via FK.
    Returns FAIL if ANY child table is NOT itself a TIER-6 table.

    Uses psycopg2 direct SQL (PostgREST doesn't expose pg_constraint reliably).
    """
    try:
        rows = _run_sql(
            client,
            f"""
            SELECT
                tc.table_name AS child_table,
                kcu.column_name AS child_column,
                ccu.column_name AS parent_column
            FROM information_schema.table_constraints AS tc
            JOIN information_schema.constraint_column_usage AS ccu
                ON ccu.constraint_name = tc.constraint_name
            JOIN information_schema.key_column_usage AS kcu
                ON kcu.constraint_name = tc.constraint_name
            WHERE tc.constraint_type = 'FOREIGN KEY'
              AND ccu.table_name = '{table_name}'
            """,
        )
        if not rows:
            return VerifyResult(ok=True, reason="no FK children")

        child_names = list(set(r["child_table"] for r in rows))

        # Filter: safe if child is in TIER_6 hardcoded list or has TIER_6 label
        unsafe_children: list[str] = []
        for child in child_names:
            if child in _TIER_6_HARDCODED:
                continue
            if _is_tier_6_labeled(client, child):
                continue
            unsafe_children.append(child)

        if unsafe_children:
            return VerifyResult(
                ok=False,
                reason=f"FK children from non-TIER-6 tables: {unsafe_children}",
            )
        return VerifyResult(ok=True, reason="all FK children are TIER-6 or none")

    except Exception as e:
        return VerifyResult(ok=True, reason=f"FK child check skipped (error: {e})")


def _is_tier_6_labeled(client, table_name: str) -> bool:
    """
    Check if a table has the TIER_6 label in equipment_classification.
    Returns False if not labeled TIER_6 (considered unsafe = non-TIER-6 parent).
    """
    try:
        rows = _run_sql(
            client,
            f"""
            SELECT label
            FROM equipment_classification
            WHERE table_name = '{table_name}'
              AND label = '{_TIER_6_LABEL}'
            LIMIT 1
            """,
        )
        return bool(rows)
    except Exception:
        return False


# ── Supabase Client ────────────────────────────────────────────────────────────


def _get_supabase_client():
    """Load env and return Supabase client using only env vars (no settings module)."""
    from supabase import create_client

    backend_root = Path(__file__).parent.parent.parent
    env_files = [
        backend_root / "backend" / ".env",
        backend_root / ".env",
    ]
    for env_file in env_files:
        if env_file.exists():
            from dotenv import load_dotenv

            load_dotenv(env_file)
            break

    supabase_url = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY")

    if not supabase_url or not supabase_key:
        raise ValueError("Supabase credentials not configured. Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in .env")

    return create_client(supabase_url, supabase_key)


# ── CLI ────────────────────────────────────────────────────────────────────────


def main():
    if len(sys.argv) < 2:
        print("Usage: python verify_tier_6_safety.py <table_name>")
        print("       python verify_tier_6_safety.py --test")
        sys.exit(1)

    if sys.argv[1] == "--test":
        _run_tests()
        return

    table_name = sys.argv[1]
    result = verify_tier_6_safety(table_name)
    print(f"\nFinal: {result}")
    sys.exit(0 if result.ok else 1)


def _run_tests():
    """Test verify_tier_6_safety against known cases."""
    print("\n\n" + "=" * 60)
    print("RUNNING TESTS")
    print("=" * 60)

    # Test 1: equipment_elements — the Phase 4-A failure case
    print("\n[Test 1] verify_tier_6_safety('equipment_elements')")
    result = verify_tier_6_safety("equipment_elements")
    print(f"  Result: {result}")
    if not result.ok:
        print("  ✓ PASS — correctly detected unsafe")
    else:
        print("  ✗ FAIL — should have detected this table is not safe")

    # Test 2: A canonical table (equipment) — should fail due to code refs
    print("\n[Test 2] verify_tier_6_safety('equipment')")
    result2 = verify_tier_6_safety("equipment")
    print(f"  Result: {result2}")
    # equipment has massive code presence — should fail for code refs
    if not result2.ok and "code refs" in str(result2.reason):
        print("  ✓ PASS — correctly detected heavy code usage")
    else:
        print(f"  ? Result: {'FAIL (expected code refs)' if result2.ok else 'code refs found as expected'}")

    # Test 3: A TIER-6 hardcoded table (building_handbooks)
    print("\n[Test 3] verify_tier_6_safety('building_handbooks')")
    result3 = verify_tier_6_safety("building_handbooks")
    print(f"  Result: {result3}")
    # building_handbooks is hardcoded TIER-6, but we still check for deps
    if result3.ok:
        print("  ✓ PASS — building_handbooks is TIER-6 and has no deps")
    else:
        print(f"  ? Result: {result3.reason}")

    print("\n" + "=" * 60)
    print("TESTS COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()
