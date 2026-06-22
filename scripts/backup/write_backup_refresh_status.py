#!/usr/bin/env python3
"""Persist the latest local backup restore status for the health dashboard."""

from __future__ import annotations

import json
import argparse
from datetime import datetime, timezone
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("status_file")
    parser.add_argument("result")
    parser.add_argument("refreshed_at")
    parser.add_argument("database")
    parser.add_argument("container_name")
    parser.add_argument("--backup-dir")
    parser.add_argument("--duration-seconds", type=float)
    parser.add_argument("--table-count", type=int)
    parser.add_argument("--database-size-bytes", type=int)
    parser.add_argument("--critical-row-counts-json")
    parser.add_argument("--message")
    args = parser.parse_args()

    critical_row_counts = {}
    if args.critical_row_counts_json:
        try:
            parsed = json.loads(args.critical_row_counts_json)
            if isinstance(parsed, dict):
                critical_row_counts = parsed
        except json.JSONDecodeError:
            critical_row_counts = {"_parse_error": args.critical_row_counts_json}

    status_file = Path(args.status_file)
    payload = {
        "result": args.result,
        "refreshed_at": args.refreshed_at,
        "database": args.database,
        "container_name": args.container_name,
        "backup_dir": args.backup_dir,
        "duration_seconds": args.duration_seconds,
        "table_count": args.table_count,
        "database_size_bytes": args.database_size_bytes,
        "critical_row_counts": critical_row_counts,
        "message": args.message,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    status_file.parent.mkdir(parents=True, exist_ok=True)
    status_file.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
