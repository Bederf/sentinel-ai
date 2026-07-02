#!/usr/bin/env python3
"""Report-only Phase 185 chiller input-contract smoke test.

Loads registered site-002 chiller LSTM/autoencoder candidates without activating
them, builds their declared input-contract feature windows from telemetry_hourly,
and reports whether inference can run without missing-feature zero-fill.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import joblib
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.ml_inference import _fetch_contract_sensor_window_from_db
from ml.autoencoder.model import SensorAutoencoder
from ml.lstm.model import SensorLSTM
from ml.registry import ModelRegistry


def _candidate_models(registry: ModelRegistry, site_id: str, equipment_type: str) -> list[dict[str, Any]]:
    models = registry.list_models(equipment_type=equipment_type, site_id=site_id)
    result = []
    for model_type in ("lstm", "autoencoder"):
        candidates = [
            model
            for model in models
            if model.get("model_type") == model_type
            and model.get("status") == "registered"
            and (model.get("metadata") or {}).get("data_source") == "telemetry_hourly"
        ]
        if candidates:
            result.append(candidates[0])
    return result


def _scale_window(model_info: dict[str, Any], data: np.ndarray) -> np.ndarray:
    scaler_path = (model_info.get("metadata") or {}).get("scaler_path")
    if scaler_path and Path(scaler_path).exists():
        scaler = joblib.load(scaler_path)
        original_shape = data.shape
        flat = data.reshape(-1, data.shape[-1])
        return scaler.transform(flat).reshape(original_shape)
    return data


def _smoke_model(model_info: dict[str, Any], *, site_id: str, equipment_code: str) -> dict[str, Any]:
    model_type = model_info.get("model_type")
    hours = 168 if model_type == "lstm" else 24
    contract_result = _fetch_contract_sensor_window_from_db(
        equipment_code=equipment_code,
        equipment_type=str(model_info.get("equipment_type")),
        hours=hours,
        model_info=model_info,
        site_id=site_id,
    )
    report: dict[str, Any] = {
        "model_id": model_info.get("model_id"),
        "model_type": model_type,
        "status": model_info.get("status"),
        "contract_diagnostics": contract_result.diagnostics,
        "serving_mutated": False,
    }
    if contract_result.error or contract_result.data is None:
        report["result"] = "model_unavailable"
        report["error"] = contract_result.error
        return report

    data = _scale_window(model_info, contract_result.data)
    if model_type == "lstm":
        model = SensorLSTM.load(str(model_info["model_path"]))
        prediction = model.predict(data.reshape(1, data.shape[0], data.shape[1]))[0]
        report["result"] = "pass"
        report["prediction"] = [float(value) for value in prediction]
        return report

    if model_type == "autoencoder":
        model = SensorAutoencoder.load(str(model_info["model_path"]))
        is_anomaly, scores = model.is_anomaly(data.reshape(1, data.shape[0], data.shape[1]))
        report["result"] = "pass"
        report["is_anomaly"] = bool(is_anomaly[0])
        report["anomaly_score"] = float(scores[0])
        report["threshold"] = float(model.threshold) if model.threshold is not None else None
        return report

    report["result"] = "unsupported_model_type"
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke S002 chiller input contract without activation.")
    parser.add_argument("--site-id", default="site-002")
    parser.add_argument("--equipment-type", default="chiller")
    parser.add_argument("--equipment-code", default="S002-CHILLER-TYPE")
    parser.add_argument(
        "--database-url",
        default="postgresql://postgres:postgres@127.0.0.1:55322/postgres",
        help="Direct Postgres URL for telemetry_hourly",
    )
    parser.add_argument(
        "--registry",
        type=Path,
        default=ROOT / "ml" / "models" / "registry.json",
        help="Path to registry.json",
    )
    args = parser.parse_args()

    os.environ["DATABASE_URL"] = args.database_url
    registry = ModelRegistry(registry_path=str(args.registry))
    candidates = _candidate_models(registry, args.site_id, args.equipment_type)
    report = {
        "site_id": args.site_id,
        "equipment_type": args.equipment_type,
        "candidate_count": len(candidates),
        "mutated_registry": False,
        "models": [
            _smoke_model(model, site_id=args.site_id, equipment_code=args.equipment_code) for model in candidates
        ],
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if candidates and all(item.get("result") == "pass" for item in report["models"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
