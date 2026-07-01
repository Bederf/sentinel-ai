#!/usr/bin/env python3
"""Report active ML models whose registry provenance looks synthetic.

This script is intentionally read-only. It scans registry.json for active LSTM
and autoencoder entries with known demo-data sample-count signatures while
metadata claims `use_demo_data=false` or omits an explicit data source.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


LSTM_SIGNATURES = {(4000, 1000)}
AUTOENCODER_SIGNATURES = {(294, 74), (298, 75), (301, 76)}


def _metadata(entry: dict[str, Any]) -> dict[str, Any]:
    metadata = entry.get("metadata")
    return metadata if isinstance(metadata, dict) else {}


def _signature_for(entry: dict[str, Any]) -> tuple[int | None, int | None]:
    metadata = _metadata(entry)
    return metadata.get("training_samples"), metadata.get("validation_samples")


def _is_false_provenance_candidate(entry: dict[str, Any]) -> bool:
    if entry.get("status") != "active":
        return False
    metadata = _metadata(entry)
    signature = _signature_for(entry)
    model_type = entry.get("model_type")
    if model_type == "lstm" and signature not in LSTM_SIGNATURES:
        return False
    if model_type == "autoencoder" and signature not in AUTOENCODER_SIGNATURES:
        return False
    if model_type not in {"lstm", "autoencoder"}:
        return False
    return metadata.get("use_demo_data") is False and not metadata.get("data_source")


def scan_registry(registry_path: Path) -> list[dict[str, Any]]:
    registry = json.loads(registry_path.read_text())
    findings: list[dict[str, Any]] = []
    for active_key, model_id in sorted((registry.get("active") or {}).items()):
        entry = (registry.get("models") or {}).get(model_id)
        if not entry or not _is_false_provenance_candidate(entry):
            continue
        training_samples, validation_samples = _signature_for(entry)
        findings.append(
            {
                "active_key": active_key,
                "model_id": model_id,
                "model_type": entry.get("model_type"),
                "equipment_type": entry.get("equipment_type"),
                "site_id": entry.get("site_id") or _metadata(entry).get("site_id"),
                "training_samples": training_samples,
                "validation_samples": validation_samples,
                "use_demo_data": _metadata(entry).get("use_demo_data"),
                "data_source": _metadata(entry).get("data_source"),
            }
        )
    return findings


def _load_trainable_site_overlap(equipment_types: set[str]) -> dict[str, list[str]]:
    """Return equipment_type -> trainable site list when DATABASE_URL is configured."""
    try:
        import psycopg2
        from app.config.settings import settings

        if not settings.database_url:
            return {}
        conn = psycopg2.connect(settings.database_url)
        cur = conn.cursor()
        cur.execute(
            """
            SELECT equipment_type, site_id
            FROM public.ml_model_config
            WHERE ml_trainable IS TRUE
              AND equipment_type = ANY(%s)
            ORDER BY equipment_type, site_id
            """,
            [list(equipment_types)],
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()
    except Exception:
        return {}

    overlap: dict[str, list[str]] = {}
    for equipment_type, site_id in rows:
        if not site_id:
            continue
        overlap.setdefault(equipment_type, []).append(site_id)
    return overlap


def build_report(registry_path: Path) -> dict[str, Any]:
    findings = scan_registry(registry_path)
    overlap = _load_trainable_site_overlap({f["equipment_type"] for f in findings if f.get("equipment_type")})
    for finding in findings:
        equipment_type = finding.get("equipment_type")
        finding["confirmed_trainable_sites"] = (
            overlap.get(equipment_type, []) if isinstance(equipment_type, str) else []
        )
        finding["global_inference_exposure"] = finding.get("site_id") is None
    return {
        "registry_path": str(registry_path),
        "false_provenance_active_models": len(findings),
        "findings": findings,
        "mutated_registry": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit ML model registry provenance without mutating state.")
    parser.add_argument(
        "--registry",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "ml" / "models" / "registry.json",
        help="Path to registry.json",
    )
    args = parser.parse_args()

    report = build_report(args.registry)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 1 if report["false_provenance_active_models"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
