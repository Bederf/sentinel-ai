#!/usr/bin/env python3
"""Read-only Phase 188 outcome validation report."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import psycopg2
import psycopg2.extras


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.services.phase188_outcome_validation_service import (  # noqa: E402
    Phase188OutcomeValidationService,
    SafetyProfile,
    threshold_from_row,
)


DB_URL = os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:55322/postgres")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a report-only Phase 188 outcome validation snapshot.")
    parser.add_argument("--database-url", default=DB_URL, help="Postgres connection URL.")
    parser.add_argument("--site-id", default="site-002", help="Site code to report.")
    parser.add_argument("--limit", type=int, default=5000, help="Maximum recommendation rows to inspect.")
    return parser.parse_args()


def connect(database_url: str):
    return psycopg2.connect(database_url, cursor_factory=psycopg2.extras.RealDictCursor)


def fetch_recommendations(conn, site_id: str, limit: int) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            select id::text,
                   site_id,
                   action_type,
                   target_equipment,
                   action,
                   expected_impact,
                   status,
                   outcome_validated,
                   outcome_notes,
                   actual_saving_kwh,
                   actual_saving_zar,
                   metadata,
                   phase188_evidence_epoch
            from public.recommendations
            where site_id = %s
            order by timestamp desc
            limit %s
            """,
            [site_id, limit],
        )
        return [dict(row) for row in cur.fetchall()]


def fetch_safety_profiles(conn, site_id: str) -> list[SafetyProfile]:
    with conn.cursor() as cur:
        cur.execute(
            """
            select site_id, equipment_type, default_safety_class, source, reason
            from public.phase188_equipment_safety_profiles
            where enabled is true
              and (site_id is null or site_id = '' or site_id = %s)
            """,
            [site_id],
        )
        rows = cur.fetchall()
    return [
        SafetyProfile(
            site_id=row.get("site_id") or None,
            equipment_type=str(row.get("equipment_type") or "").lower(),
            default_safety_class=str(row.get("default_safety_class") or "HIGH").upper(),
            source=str(row.get("source") or "equipment_type_profile"),
            reason=str(row.get("reason") or ""),
        )
        for row in rows
    ]


def fetch_thresholds(conn, site_id: str):
    with conn.cursor() as cur:
        cur.execute(
            """
            select *
            from public.phase188_outcome_thresholds
            where enabled is true
              and (site_id is null or site_id = '' or site_id = %s)
            """,
            [site_id],
        )
        rows = cur.fetchall()
    return [threshold_from_row(dict(row)) for row in rows]


def fetch_epoch_counts(conn, site_id: str) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            select phase188_evidence_epoch, count(*)::int as rows
            from public.recommendations
            where site_id = %s
            group by phase188_evidence_epoch
            order by phase188_evidence_epoch
            """,
            [site_id],
        )
        return [dict(row) for row in cur.fetchall()]


def main() -> int:
    args = parse_args()
    with connect(args.database_url) as conn:
        rows = fetch_recommendations(conn, args.site_id, args.limit)
        profiles = fetch_safety_profiles(conn, args.site_id)
        thresholds = fetch_thresholds(conn, args.site_id)
        report = Phase188OutcomeValidationService().evaluate_rows(
            rows,
            safety_profiles=profiles,
            thresholds=thresholds,
            site_id=args.site_id,
        )
        report["epoch_counts"] = fetch_epoch_counts(conn, args.site_id)
        report["safety_profile_count"] = len(profiles)
        report["threshold_count"] = len(thresholds)
    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
