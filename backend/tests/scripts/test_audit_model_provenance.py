import json

from scripts.audit_model_provenance import scan_registry


def test_scan_registry_flags_active_lstm_demo_signature_false_provenance(tmp_path):
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(
        json.dumps(
            {
                "active": {"lstm_chiller": "lstm_chiller_20260701"},
                "models": {
                    "lstm_chiller_20260701": {
                        "model_id": "lstm_chiller_20260701",
                        "model_type": "lstm",
                        "equipment_type": "chiller",
                        "model_path": "lstm/chiller.h5",
                        "metrics": {},
                        "metadata": {
                            "training_samples": 4000,
                            "validation_samples": 1000,
                            "use_demo_data": False,
                        },
                        "registered_at": "2026-07-01T00:00:00",
                        "status": "active",
                    }
                },
            }
        )
    )

    findings = scan_registry(registry_path)

    assert len(findings) == 1
    assert findings[0]["model_id"] == "lstm_chiller_20260701"
    assert findings[0]["training_samples"] == 4000


def test_scan_registry_does_not_flag_honest_synthetic_metadata(tmp_path):
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(
        json.dumps(
            {
                "active": {"autoencoder_ahu": "autoencoder_ahu_20260701"},
                "models": {
                    "autoencoder_ahu_20260701": {
                        "model_id": "autoencoder_ahu_20260701",
                        "model_type": "autoencoder",
                        "equipment_type": "ahu",
                        "model_path": "autoencoder/ahu.h5",
                        "metrics": {},
                        "metadata": {
                            "training_samples": 298,
                            "validation_samples": 75,
                            "use_demo_data": True,
                            "data_source": "synthetic_fallback",
                        },
                        "registered_at": "2026-07-01T00:00:00",
                        "status": "active",
                    }
                },
            }
        )
    )

    assert scan_registry(registry_path) == []
