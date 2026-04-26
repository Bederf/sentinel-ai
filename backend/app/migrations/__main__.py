"""Run migration runner directly: python -m app.migrations --dry-run"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

# Ensure backend is on path for imports (must precede the runner import below)
_backend_path = Path(__file__).parent.parent.parent
if str(_backend_path) not in sys.path:
    sys.path.insert(0, str(_backend_path))

from app.migrations.runner import run_pending_migrations  # noqa: E402

logger = logging.getLogger("sentinel.migrations")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run SQL migrations")
    parser.add_argument("--dry-run", action="store_true", help="Log actions without executing")
    args = parser.parse_args()

    dry_run = os.getenv("MIGRATION_DRY_RUN", "false").lower() == "true" or args.dry_run

    if dry_run:
        logger.warning("MIGRATION DRY RUN — no files will be applied")

    applied = run_pending_migrations(dry_run=dry_run)
    if applied:
        print(f"Applied: {applied}")
    else:
        print("No pending migrations")
