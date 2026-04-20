#!/usr/bin/env python3
"""Non-destructive registry pruner for SENTINEL ML model registry.

Archives inactive model entries from registry.json to registry.bak.json.
Run manually before edge deployment to shrink active registry footprint.

Usage:
    python -m backend.scripts.registry_pruner
    python -m backend.scripts.registry_pruner --registry-path /custom/path/registry.json
    python -m backend.scripts.registry_pruner --dry-run
"""

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

DEFAULT_REGISTRY = Path(__file__).parent.parent / "ml" / "models" / "registry.json"
DEFAULT_BACKUP = Path(__file__).parent.parent / "ml" / "models" / "registry.bak.json"


def load_registry(path: Path) -> dict:
    """Load registry JSON from disk.

    Raises:
        FileNotFoundError: if the registry file does not exist.
        json.JSONDecodeError: if the file content is not valid JSON.
    """
    if not path.exists():
        raise FileNotFoundError(f"Registry file not found: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise json.JSONDecodeError(f"Registry file is corrupt ({path}): {exc.msg}", exc.doc, exc.pos) from exc


def partition_models(registry: dict) -> tuple[dict, dict]:
    """Split registry models into active and inactive.

    Args:
        registry: Full registry dict with "models" key.

    Returns:
        (active_models, inactive_models) — both are sub-dicts keyed by model_id.
    """
    models = registry.get("models", {})
    active_models = {k: v for k, v in models.items() if v.get("status") == "active"}
    inactive_models = {k: v for k, v in models.items() if v.get("status") != "active"}
    return active_models, inactive_models


def stamp_archived_entries(inactive_models: dict) -> dict:
    """Add 'archived_at' timestamp to each model entry (without mutating originals).

    Args:
        inactive_models: Dict of model_id -> model entry dicts.

    Returns:
        New dict with copied+stamped entries.
    """
    archived_at = datetime.now(UTC).isoformat()
    stamped = {}
    for model_id, entry in inactive_models.items():
        stamped[model_id] = {**entry, "archived_at": archived_at}
    return stamped


def load_backup(path: Path) -> dict:
    """Load existing backup file or return a fresh schema-v1 structure.

    Args:
        path: Path to the backup JSON file.

    Returns:
        Backup dict with "schema_version" and "entries" keys.
    """
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"schema_version": 1, "entries": []}


def append_to_backup(backup: dict, stamped_inactive: dict, registry_path: Path) -> None:
    """Append a new batch entry to the backup's entries list (mutates backup in-place).

    Args:
        backup: The backup dict (modified in-place).
        stamped_inactive: Stamped model entries to archive.
        registry_path: Path of the source registry (used for provenance).
    """
    batch = {
        "archived_at": datetime.now(UTC).isoformat(),
        "pruned_from": registry_path.name,
        "model_count": len(stamped_inactive),
        "models": stamped_inactive,
    }
    backup["entries"].append(batch)


def atomic_write(path: Path, data: dict) -> None:
    """Write data to a file atomically (tmp → rename on POSIX).

    Args:
        path: Destination file path.
        data: JSON-serialisable dict.
    """
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    tmp.rename(path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Archive inactive models from registry.json to registry.bak.json.")
    parser.add_argument(
        "--registry-path",
        type=Path,
        default=DEFAULT_REGISTRY,
        help="Path to the source registry.json (default: backend/ml/models/registry.json)",
    )
    parser.add_argument(
        "--backup-path",
        type=Path,
        default=DEFAULT_BACKUP,
        help="Path to the backup file (default: backend/ml/models/registry.bak.json)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print summary without writing any files.",
    )
    args = parser.parse_args()

    registry_path: Path = args.registry_path
    backup_path: Path = args.backup_path

    # Load and partition
    registry = load_registry(registry_path)
    active_models, inactive_models = partition_models(registry)

    print(f"Found {len(inactive_models)} inactive, {len(active_models)} active models")

    if args.dry_run:
        print("[dry-run] No files written.")
        return

    if not inactive_models:
        print("Nothing to archive. Registry is already clean.")
        return

    # Stamp inactive entries with archived_at
    stamped_inactive = stamp_archived_entries(inactive_models)

    # Load or create backup and append the new batch
    backup = load_backup(backup_path)
    append_to_backup(backup, stamped_inactive, registry_path)

    # Build pruned registry (active models only; preserve "active" dict unchanged)
    pruned_registry = {
        "models": active_models,
        "active": registry.get("active", {}),
    }

    # Write backup first, then pruned registry (atomic writes)
    atomic_write(backup_path, backup)
    atomic_write(registry_path, pruned_registry)

    # Verify the pruned registry is valid JSON
    try:
        json.loads(registry_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"ERROR: Pruned registry is corrupt after write: {exc}", file=sys.stderr)
        sys.exit(1)

    total_archived = sum(e["model_count"] for e in backup["entries"])
    print(
        f"Done. registry.json: {len(active_models)} active models. registry.bak.json: {total_archived} archived models."
    )


if __name__ == "__main__":
    main()
