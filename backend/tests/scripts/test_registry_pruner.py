"""Tests for backend.scripts.registry_pruner.

All tests operate on in-memory fixtures or tmp_path — no real registry.json touched.
"""

import json
from datetime import datetime
from pathlib import Path

from scripts.registry_pruner import (
    append_to_backup,
    atomic_write,
    partition_models,
    stamp_archived_entries,
)

# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------

SAMPLE_REGISTRY = {
    "models": {
        "lstm_chiller_active": {
            "model_id": "lstm_chiller_active",
            "model_type": "lstm",
            "equipment_type": "chiller",
            "status": "active",
        },
        "lstm_ahu_active": {
            "model_id": "lstm_ahu_active",
            "model_type": "lstm",
            "equipment_type": "ahu",
            "status": "active",
        },
        "lstm_old_001": {
            "model_id": "lstm_old_001",
            "model_type": "lstm",
            "equipment_type": "chiller",
            "status": "inactive",
        },
        "lstm_old_002": {
            "model_id": "lstm_old_002",
            "model_type": "lstm",
            "equipment_type": "ahu",
            "status": "inactive",
        },
    },
    "active": {
        "lstm_chiller": "lstm_chiller_active",
        "lstm_ahu": "lstm_ahu_active",
    },
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_partition_models_splits_correctly():
    active, inactive = partition_models(SAMPLE_REGISTRY)

    assert "lstm_chiller_active" in active
    assert "lstm_ahu_active" in active
    assert "lstm_old_001" in inactive
    assert "lstm_old_002" in inactive

    # Cross-check: nothing appears in both buckets
    assert set(active.keys()).isdisjoint(set(inactive.keys()))

    # Counts
    assert len(active) == 2
    assert len(inactive) == 2


def test_stamp_archived_entries_adds_datestamp():
    _, inactive = partition_models(SAMPLE_REGISTRY)
    stamped = stamp_archived_entries(inactive)

    for entry in stamped.values():
        assert "archived_at" in entry
        # Must be a valid ISO timestamp
        datetime.fromisoformat(entry["archived_at"])


def test_stamp_does_not_mutate_original():
    _, inactive = partition_models(SAMPLE_REGISTRY)
    original_keys = set(inactive["lstm_old_001"].keys())

    stamp_archived_entries(inactive)

    # Original entry must not have been mutated
    assert set(inactive["lstm_old_001"].keys()) == original_keys
    assert "archived_at" not in inactive["lstm_old_001"]


def test_append_to_backup_creates_entry():
    backup = {"schema_version": 1, "entries": []}
    _, inactive = partition_models(SAMPLE_REGISTRY)
    stamped = stamp_archived_entries(inactive)

    append_to_backup(backup, stamped, Path("registry.json"))

    assert len(backup["entries"]) == 1
    entry = backup["entries"][0]
    assert entry["model_count"] == 2
    assert "models" in entry
    assert "archived_at" in entry
    assert entry["pruned_from"] == "registry.json"


def test_append_to_backup_preserves_existing_entries():
    backup = {"schema_version": 1, "entries": [{"archived_at": "old", "models": {}}]}
    _, inactive = partition_models(SAMPLE_REGISTRY)

    append_to_backup(backup, stamp_archived_entries(inactive), Path("registry.json"))

    assert len(backup["entries"]) == 2  # old entry preserved + new entry


def test_atomic_write_produces_valid_json(tmp_path):
    path = tmp_path / "test.json"
    atomic_write(path, {"key": "value"})

    assert json.loads(path.read_text()) == {"key": "value"}
    # Temp file must be cleaned up after rename
    assert not (tmp_path / "test.tmp").exists()


def test_dry_run_does_not_write(tmp_path, monkeypatch):
    import sys

    registry_path = tmp_path / "registry.json"
    backup_path = tmp_path / "registry.bak.json"
    registry_path.write_text(json.dumps(SAMPLE_REGISTRY))

    original_content = registry_path.read_text()

    # Simulate --dry-run by calling main() with patched sys.argv and patched paths
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "registry_pruner",
            "--registry-path",
            str(registry_path),
            "--backup-path",
            str(backup_path),
            "--dry-run",
        ],
    )

    from scripts.registry_pruner import main

    main()

    # Registry file must not have been modified
    assert registry_path.read_text() == original_content
    # Backup must not have been created
    assert not backup_path.exists()
