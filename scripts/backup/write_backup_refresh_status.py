#!/usr/bin/env python3
"""Persist the latest standby refresh status for the health dashboard."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 6:
        print(
            "usage: write_backup_refresh_status.py <status-file> <result> <refreshed-at> <database> <container-name>",
            file=sys.stderr,
        )
        return 1

    status_file = Path(sys.argv[1])
    payload = {
        "result": sys.argv[2],
        "refreshed_at": sys.argv[3],
        "database": sys.argv[4],
        "container_name": sys.argv[5],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    status_file.parent.mkdir(parents=True, exist_ok=True)
    status_file.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
