#!/usr/bin/env python3
"""Auto-prune old RLM runner output directories.

Deletes run output folders older than the retention period while always
keeping a minimum number of recent runs per case.

Safety guards:
  - Base path is HARDCODED to /var/lib/sentinel/rlm_out/ (never parameterized)
  - All paths are resolved and validated to be under the base path
  - Symlinks are never followed or deleted
  - Dry-run mode prints what would be deleted without deleting
  - All deletions are logged to stdout (cron captures to journal)

Usage:
  python prune-rlm-outputs.py [--dry-run] [--retention-days 90] [--keep-min 5]

Intended cron entry:
  0 3 * * 0 /opt/rlm-runner/venv/bin/python /opt/bms-intelligence/infra/scripts/prune-rlm-outputs.py

Phase: 113-03
See: docs/02-architecture/SENTINEL-RLM-ARCHITECTURE-SPEC-v1.0.md Section 8.2
"""

import argparse
import os
import shutil
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

# HARDCODED base path — never accept this from arguments or environment
BASE_PATH = Path("/var/lib/sentinel/rlm_out")


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Prune old RLM runner output directories.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Print what would be deleted without actually deleting.",
    )
    parser.add_argument(
        "--retention-days",
        type=int,
        default=90,
        help="Delete outputs older than this many days (default: 90).",
    )
    parser.add_argument(
        "--keep-min",
        type=int,
        default=5,
        help="Always keep at least this many most recent runs per case (default: 5).",
    )
    return parser.parse_args()


def validate_path(path: Path) -> bool:
    """Validate that a resolved path is safely under BASE_PATH."""
    try:
        resolved = path.resolve(strict=False)
        return str(resolved).startswith(str(BASE_PATH.resolve()))
    except (OSError, ValueError):
        return False


def is_safe_to_delete(path: Path) -> bool:
    """Check that a path is safe to delete (not a symlink, under base)."""
    if path.is_symlink():
        return False
    if not validate_path(path):
        return False
    return True


def get_run_dirs() -> dict[str, list[tuple[Path, float]]]:
    """Scan BASE_PATH for run directories grouped by case_id.

    Run ID format: {case_id}_{YYYYMMDD}_{HHMMSS}_{hex}
    Groups runs by case_id (everything before the date portion).

    Returns:
        Dict mapping case_id -> list of (path, mtime) sorted newest first.
    """
    if not BASE_PATH.exists():
        return {}

    cases: dict[str, list[tuple[Path, float]]] = {}

    for entry in BASE_PATH.iterdir():
        if not entry.is_dir():
            continue
        if entry.is_symlink():
            continue
        if not validate_path(entry):
            continue

        # Extract case_id: everything before the date segment
        # Run ID format: CASEID_YYYYMMDD_HHMMSS_hex
        name = entry.name
        parts = name.rsplit("_", 3)
        if len(parts) >= 4:
            case_id = parts[0]
        else:
            # Fallback: treat whole name as case_id
            case_id = name

        try:
            mtime = entry.stat().st_mtime
        except OSError:
            continue

        cases.setdefault(case_id, []).append((entry, mtime))

    # Sort each case's runs newest first
    for case_id in cases:
        cases[case_id].sort(key=lambda x: x[1], reverse=True)

    return cases


def prune(
    retention_days: int = 90,
    keep_min: int = 5,
    dry_run: bool = False,
) -> tuple[int, int]:
    """Prune old run output directories.

    Args:
        retention_days: Delete outputs older than this many days.
        keep_min: Always keep at least this many recent runs per case.
        dry_run: If True, only print what would be deleted.

    Returns:
        Tuple of (directories_deleted, directories_kept).
    """
    cutoff_time = time.time() - (retention_days * 86400)
    cutoff_date = datetime.fromtimestamp(cutoff_time).isoformat()

    print(f"Prune settings: retention={retention_days}d, keep_min={keep_min}, dry_run={dry_run}")
    print(f"Cutoff date: {cutoff_date}")
    print(f"Base path: {BASE_PATH}")
    print()

    if not BASE_PATH.exists():
        print(f"Base path does not exist: {BASE_PATH}")
        return 0, 0

    cases = get_run_dirs()
    deleted = 0
    kept = 0

    for case_id, runs in sorted(cases.items()):
        print(f"Case: {case_id} ({len(runs)} runs)")

        for idx, (path, mtime) in enumerate(runs):
            # Always keep the minimum number of recent runs
            if idx < keep_min:
                print(f"  KEEP (min-{idx + 1}/{keep_min}): {path.name}")
                kept += 1
                continue

            # Check retention
            if mtime >= cutoff_time:
                print(f"  KEEP (recent): {path.name}")
                kept += 1
                continue

            # Safe to delete
            if not is_safe_to_delete(path):
                print(f"  SKIP (unsafe): {path.name}")
                kept += 1
                continue

            run_date = datetime.fromtimestamp(mtime).isoformat()
            if dry_run:
                print(f"  WOULD DELETE: {path.name} (modified: {run_date})")
            else:
                print(f"  DELETE: {path.name} (modified: {run_date})")
                try:
                    shutil.rmtree(path)
                except OSError as exc:
                    print(f"  ERROR deleting {path.name}: {exc}")
                    kept += 1
                    continue
            deleted += 1

    print()
    action = "Would delete" if dry_run else "Deleted"
    print(f"{action} {deleted} directories, kept {kept} directories.")
    return deleted, kept


def main() -> int:
    """Entry point."""
    args = parse_args()

    if args.retention_days < 1:
        print("ERROR: --retention-days must be >= 1")
        return 1

    if args.keep_min < 0:
        print("ERROR: --keep-min must be >= 0")
        return 1

    prune(
        retention_days=args.retention_days,
        keep_min=args.keep_min,
        dry_run=args.dry_run,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
